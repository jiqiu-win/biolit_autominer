"""
QSAR pipeline — predict a hepatotoxicity marker's Result from molecular structure.

Mirrors Yamini's caspase notebook
(qsar_project_dili/qsar_prediction/caspase/QSAR_Caspase_GraphTransformers.ipynb),
adapted for our literature-extracted dataset:

  * chemical NAME  -> SMILES  (via PubChem; Yamini's PubChem data already had SMILES)
  * 3-class label  (increase / decrease / no significant change) with CrossEntropyLoss
                    (Yamini's task was binary Active/Inactive with BCE)
  * class weights instead of 1:1 downsampling (downsampling doesn't extend to 3 classes)
  * ONE model per marker  -> set --marker (default ALT); reusing for AST/others is a 1-word change

Models: two graph transformers (Graphormer, GraphGPS) + GraphSAGE (a classic
message-passing GNN) + classic ML (RandomForest, XGBoost) on Morgan fingerprints.

Dataset built = the "FULL" set. Conflicting chemicals are dropped (per C. Zhu):
both increase-vs-decrease AND direction-vs-"no significant change" disagreements.
Only chemicals with a single, unambiguous result type are kept.
(The high-confidence >=2-paper subset is handled separately.)

Run:
    python qsar/qsar_marker_pipeline.py --marker ALT                     # all 5 models
    python qsar/qsar_marker_pipeline.py --marker AST                     # another marker
    python qsar/qsar_marker_pipeline.py --marker ALT --models GraphSAGE  # only retrain one;
                                                                         # updates that row,
                                                                         # keeps the others

On a fresh HPC/Jupyter environment, install deps first:
    pip install rdkit pubchempy xgboost scikit-learn pandas numpy torch torch-geometric openpyxl
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------- #
#  Config
# ----------------------------------------------------------------------------- #
HERE = Path(__file__).resolve().parent
# Up-to-date biolit dataset (Findings sheet). Override on the HPC with --data.
DATA_XLSX = Path("/Users/qiuji/Downloads/biolit_dataset (6).xlsx")
DATA_SHEET = "Findings"
SMILES_CACHE = HERE / "cache" / "name_to_smiles.csv"   # shared across all markers
RESULTS_DIR = HERE / "results"

# Map noisy Result values -> the 3 canonical classes; anything else is dropped.
_RESULT_MAP = {
    "increase": "increase", "increased": "increase", "increases": "increase",
    "decrease": "decrease", "decreased": "decrease", "decreases": "decrease",
    "no significant change": "no significant change",
}


def _normalize_result(r):
    if pd.isna(r):
        return None
    key = str(r).strip().strip('"').strip("'").lower()
    return _RESULT_MAP.get(key)   # None -> not a canonical result -> dropped

SEED = 42
PE_DIM = 8            # Laplacian eigenvectors for GraphGPS
# Canonical label order; only the classes actually present in a marker are used.
LABEL_ORDER = ["increase", "decrease", "no significant change"]

# Graph-transformer training hyper-parameters (Yamini's first config)
GT_HIDDEN = 128
GT_HEADS = 4
GT_LAYERS = 3
GT_DROPOUT = 0.3
GT_LR = 1e-3
BATCH = 64
MAX_EPOCHS = 100
PATIENCE = 20

# All models the pipeline can train (graph models + classic ML on fingerprints)
ALL_MODELS = ["Graphormer", "GraphGPS", "GraphSAGE", "RandomForest", "XGBoost"]


# ----------------------------------------------------------------------------- #
#  Stage 1 — build the FULL dataset for one marker (labels only; no SMILES yet)
# ----------------------------------------------------------------------------- #
def build_full_dataset(marker, data_path=None, sheet=DATA_SHEET):
    """
    Return a DataFrame [chemical, label, support] for the FULL dataset.

    Reads the Findings sheet of the biolit dataset. The Result column is noisy in
    the large auto-extracted dataset, so it is normalised to the 3 canonical classes
    (increase / decrease / no significant change); other values are dropped.
    `support` = number of distinct articles (PMID, or "Source file" in the old
    format) reporting the chemical's result.

    Per C. Zhu's decision, a chemical is DROPPED as "conflicting" if its papers
    disagree in either way:
      - hard conflict : increase AND decrease
      - mixed conflict: a direction (increase/decrease) AND "no significant change"
    Only chemicals with a single, unambiguous result type are kept.
    """
    path = data_path or DATA_XLSX
    try:
        df = pd.read_excel(path, sheet_name=sheet)
    except (ValueError, KeyError):
        df = pd.read_excel(path)   # old single-sheet format

    # article-id column (new format = PMID, old format = Source file)
    art_col = "Source file" if "Source file" in df.columns else "PMID"
    df = df.dropna(subset=["Tested chemical", "Marker", "Result", art_col])
    sub = df[df["Marker"] == marker].copy()
    if sub.empty:
        raise ValueError(f"No rows for marker={marker!r}. Check the spelling.")

    # normalise noisy Result values -> 3 canonical classes; drop the rest
    n_before = len(sub)
    sub["Result"] = sub["Result"].map(_normalize_result)
    sub = sub.dropna(subset=["Result"])
    print(f"[dataset] {marker}: {len(sub)}/{n_before} records with a canonical result "
          f"(dropped {n_before - len(sub)} noisy/uninterpretable)")

    papers = (
        sub.groupby(["Tested chemical", "Result"])[art_col]
        .nunique()
        .reset_index(name="n_papers")
    )

    rows, n_hard, n_mixed = [], 0, 0
    for chem, grp in papers.groupby("Tested chemical"):
        results = set(grp["Result"])
        has_inc = "increase" in results
        has_dec = "decrease" in results
        has_nc = "no significant change" in results
        if has_inc and has_dec:                     # hard conflict -> drop
            n_hard += 1
            continue
        if has_nc and (has_inc or has_dec):          # direction + no-change -> drop
            n_mixed += 1
            continue
        best = grp.sort_values("n_papers", ascending=False).iloc[0]
        rows.append(
            {"chemical": chem, "label": best["Result"], "support": int(best["n_papers"])}
        )

    full = pd.DataFrame(rows)
    print(f"[dataset] marker={marker}: {len(full)} chemicals kept "
          f"(dropped {n_hard} increase-vs-decrease + {n_mixed} direction-vs-no-change)")
    print(full["label"].value_counts().to_string())
    return full


# ----------------------------------------------------------------------------- #
#  Stage 2 — resolve chemical NAME -> SMILES via PubChem (cached, shared)
# ----------------------------------------------------------------------------- #
def _load_cache():
    if SMILES_CACHE.exists():
        c = pd.read_csv(SMILES_CACHE)
        # Empty SMILES cells come back from CSV as NaN (float). Coerce to "" so a
        # float NaN never flows downstream to RDKit -- MolFromSmiles(float) segfaults
        # on some Linux rdkit builds (raises TypeError on macOS, hence CI missed it).
        # fillna BEFORE astype, since str(NaN) would otherwise become the string "nan".
        c["smiles"] = c["smiles"].fillna("").astype(str)
        return dict(zip(c["chemical"], c["smiles"]))
    return {}


def _save_cache(cache):
    SMILES_CACHE.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [{"chemical": k, "smiles": v} for k, v in cache.items()]
    ).to_csv(SMILES_CACHE, index=False)


def resolve_smiles(names, sleep=0.2):
    """
    Map each chemical name -> SMILES using PubChem, caching results to disk so it
    only ever runs once per name (shared across markers). Unresolved names get "".
    """
    import pubchempy as pcp

    cache = _load_cache()
    todo = [n for n in names if n not in cache]
    print(f"[smiles] {len(names)} names; {len(cache)} cached; resolving {len(todo)} new ...")

    for i, name in enumerate(todo, 1):
        smi = ""
        try:
            comps = pcp.get_compounds(str(name), "name")
            if comps:
                smi = comps[0].isomeric_smiles or comps[0].canonical_smiles or ""
        except Exception:
            smi = ""
        cache[name] = smi
        if i % 25 == 0:
            print(f"  resolved {i}/{len(todo)} ...")
            _save_cache(cache)
        time.sleep(sleep)   # be polite to PubChem (~5 req/s max)

    _save_cache(cache)
    resolved = {n: cache.get(n, "") for n in names}
    n_ok = sum(1 for v in resolved.values() if v)
    print(f"[smiles] resolved {n_ok}/{len(names)} "
          f"(dropped {len(names) - n_ok} unresolvable: mixtures/extracts/combos)")
    return resolved


# ----------------------------------------------------------------------------- #
#  Stage 3 — molecule -> graph  (atom/bond features copied from Yamini's notebook)
# ----------------------------------------------------------------------------- #
def _rdkit():
    from rdkit import Chem
    from rdkit.Chem import rdchem
    return Chem, rdchem


ATOM_SYMBOLS = [6, 7, 8, 16, 9, 15, 17, 35, 53]   # C N O S F P Cl Br I
ATOM_DIM = 27
BOND_DIM = 6


def _one_hot(val, choices):
    vec = [0] * len(choices)
    try:
        vec[choices.index(val)] = 1
    except ValueError:
        pass
    return vec


def canonicalize(smi):
    Chem, _ = _rdkit()
    try:
        mol = Chem.MolFromSmiles(str(smi))
        return Chem.MolToSmiles(mol) if mol else None
    except Exception:
        return None


def atom_feat(atom):
    _, rdchem = _rdkit()
    hybrid_map = {
        rdchem.HybridizationType.SP: 0,
        rdchem.HybridizationType.SP2: 1,
        rdchem.HybridizationType.SP3: 2,
    }
    at_oh = _one_hot(atom.GetAtomicNum(), ATOM_SYMBOLS) + [0]          # 10
    deg = min(atom.GetDegree(), 5)
    deg_oh = [0] * 6
    deg_oh[deg] = 1                                                     # 6
    fc = atom.GetFormalCharge()
    fc_enc = [1 if fc < 0 else 0, 1 if fc == 0 else 0, 1 if fc > 0 else 0]  # 3
    hyb = [0, 0, 0, 0]
    hyb[hybrid_map.get(atom.GetHybridization(), 3)] = 1                 # 4
    extras = [
        int(atom.GetIsAromatic()),
        int(atom.IsInRing()),
        min(atom.GetTotalNumHs(), 4) / 4.0,
        atom.GetMass() / 100.0,
    ]                                                                   # 4
    return at_oh + deg_oh + fc_enc + hyb + extras                      # 27


def bond_feat(bond):
    _, rdchem = _rdkit()
    bond_types = [
        rdchem.BondType.SINGLE, rdchem.BondType.DOUBLE,
        rdchem.BondType.TRIPLE, rdchem.BondType.AROMATIC,
    ]
    bt_oh = _one_hot(bond.GetBondType(), bond_types)                   # 4
    return bt_oh + [int(bond.GetIsConjugated()), int(bond.IsInRing())]  # 6


def mol_to_graph(smi, label_idx):
    """SMILES + integer label -> PyG Data graph (y = long class index for CrossEntropy)."""
    import torch
    from torch_geometric.data import Data

    Chem, _ = _rdkit()
    mol = Chem.MolFromSmiles(str(smi))   # str() guard: a raw float would segfault RDKit
    if mol is None or mol.GetNumAtoms() == 0:
        return None
    x = torch.tensor([atom_feat(a) for a in mol.GetAtoms()], dtype=torch.float)
    ei, ea = [], []
    for bond in mol.GetBonds():
        i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        bf = bond_feat(bond)
        ei += [[i, j], [j, i]]
        ea += [bf, bf]
    if ei:
        edge_index = torch.tensor(ei, dtype=torch.long).t().contiguous()
        edge_attr = torch.tensor(ea, dtype=torch.float)
    else:
        edge_index = torch.zeros((2, 0), dtype=torch.long)
        edge_attr = torch.zeros((0, BOND_DIM), dtype=torch.float)
    y = torch.tensor([int(label_idx)], dtype=torch.long)
    return Data(x=x, edge_index=edge_index, edge_attr=edge_attr, y=y)


def morgan_fp(smi, n_bits=2048, radius=2):
    """Morgan fingerprint (for the classic ML models)."""
    import numpy as np
    from rdkit.Chem import AllChem, DataStructs
    Chem, _ = _rdkit()
    mol = Chem.MolFromSmiles(str(smi))   # str() guard: a raw float would segfault RDKit
    if mol is None:
        return None
    bv = AllChem.GetMorganFingerprintAsBitVect(mol, radius, nBits=n_bits)
    arr = np.zeros((n_bits,), dtype=np.int8)
    DataStructs.ConvertToNumpyArray(bv, arr)
    return arr


def compute_laplacian_pe(data, k=PE_DIM):
    """Laplacian positional encoding for GraphGPS (copied from Yamini)."""
    import torch
    import torch.nn.functional as F
    from torch_geometric.utils import get_laplacian, to_dense_adj
    n = data.num_nodes
    if n <= 2:
        return torch.zeros(n, k)
    ei, ew = get_laplacian(data.edge_index, normalization="sym", num_nodes=n)
    L = to_dense_adj(ei, edge_attr=ew, max_num_nodes=n).squeeze(0).numpy()
    try:
        _, vecs = np.linalg.eigh(L)
        take = min(k, n - 1)
        pe = torch.from_numpy(vecs[:, 1:1 + take]).float()
        if pe.shape[1] < k:
            pe = F.pad(pe, (0, k - pe.shape[1]))
    except Exception:
        pe = torch.zeros(n, k)
    return pe


# ----------------------------------------------------------------------------- #
#  Stage 4 — models  (Yamini's Graphormer/GraphGPS, head adapted to n_classes)
# ----------------------------------------------------------------------------- #
def build_models_module():
    """Define the torch models lazily (so the file imports without torch present)."""
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch_geometric.nn import (TransformerConv, GINEConv, GPSConv, SAGEConv,
                                     global_mean_pool)
    from torch_geometric.utils import degree as pyg_degree

    class GraphormerLayer(nn.Module):
        def __init__(self, hidden, num_heads, edge_dim=BOND_DIM, dropout=0.3):
            super().__init__()
            head_dim = hidden // num_heads
            self.attn = TransformerConv(hidden, head_dim, heads=num_heads, concat=True,
                                        edge_dim=edge_dim, dropout=dropout, beta=True)
            self.norm1 = nn.LayerNorm(hidden)
            self.ffn = nn.Sequential(nn.Linear(hidden, hidden * 2), nn.GELU(),
                                     nn.Dropout(dropout), nn.Linear(hidden * 2, hidden))
            self.norm2 = nn.LayerNorm(hidden)
            self.drop = nn.Dropout(dropout)

        def forward(self, x, edge_index, edge_attr):
            x = self.norm1(x + self.drop(self.attn(x, edge_index, edge_attr)))
            x = self.norm2(x + self.drop(self.ffn(x)))
            return x

    class GraphormerModel(nn.Module):
        def __init__(self, n_classes, in_dim=ATOM_DIM, hidden=128, num_heads=4,
                     num_layers=3, dropout=0.3):
            super().__init__()
            torch.manual_seed(SEED)
            self.node_emb = nn.Linear(in_dim, hidden)
            self.degree_emb = nn.Embedding(100, hidden)
            self.layers = nn.ModuleList(
                [GraphormerLayer(hidden, num_heads, BOND_DIM, dropout) for _ in range(num_layers)]
            )
            self.drop = nn.Dropout(dropout)
            self.head = nn.Sequential(nn.Linear(hidden, hidden // 2), nn.ReLU(),
                                      nn.Dropout(dropout), nn.Linear(hidden // 2, n_classes))

        def forward(self, x, edge_index, edge_attr, batch):
            h = self.node_emb(x)
            deg = pyg_degree(edge_index[0], num_nodes=x.size(0)).long().clamp(max=99)
            h = F.relu(h + self.degree_emb(deg))
            h = self.drop(h)
            for layer in self.layers:
                h = layer(h, edge_index, edge_attr)
            h = global_mean_pool(h, batch)
            return self.head(h)                 # [batch, n_classes]

    class GraphGPSModel(nn.Module):
        def __init__(self, n_classes, in_dim=ATOM_DIM, hidden=128, pe_dim=PE_DIM,
                     num_heads=4, num_layers=3, dropout=0.3):
            super().__init__()
            torch.manual_seed(SEED)
            self.node_emb = nn.Linear(in_dim, hidden)
            self.pe_emb = nn.Linear(pe_dim, hidden)
            self.gps_layers = nn.ModuleList()
            for _ in range(num_layers):
                mlp = nn.Sequential(nn.Linear(hidden, hidden * 2), nn.GELU(),
                                    nn.Linear(hidden * 2, hidden))
                conv = GINEConv(mlp, edge_dim=BOND_DIM)
                self.gps_layers.append(
                    GPSConv(channels=hidden, conv=conv, heads=num_heads, dropout=dropout,
                            norm="layer_norm", attn_type="multihead")
                )
            self.drop = nn.Dropout(dropout)
            self.head = nn.Sequential(nn.Linear(hidden, hidden // 2), nn.ReLU(),
                                      nn.Dropout(dropout), nn.Linear(hidden // 2, n_classes))

        def forward(self, x, edge_index, edge_attr, batch, pe):
            h = F.relu(self.node_emb(x) + self.pe_emb(pe))
            h = self.drop(h)
            for gps in self.gps_layers:
                h = gps(h, edge_index, batch, edge_attr=edge_attr)
            h = global_mean_pool(h, batch)
            return self.head(h)                 # [batch, n_classes]

    class GraphSAGEModel(nn.Module):
        """
        GraphSAGE — a classic message-passing GNN (Hamilton et al., NeurIPS 2017).
        Uses only node features + connectivity (SAGEConv does NOT use bond/edge
        features), so it's a simpler, often-robust baseline vs. the graph transformers.
        """
        def __init__(self, n_classes, in_dim=ATOM_DIM, hidden=128, num_layers=3, dropout=0.3):
            super().__init__()
            torch.manual_seed(SEED)
            self.node_emb = nn.Linear(in_dim, hidden)
            self.convs = nn.ModuleList([SAGEConv(hidden, hidden) for _ in range(num_layers)])
            self.norms = nn.ModuleList([nn.LayerNorm(hidden) for _ in range(num_layers)])
            self.drop = nn.Dropout(dropout)
            self.head = nn.Sequential(nn.Linear(hidden, hidden // 2), nn.ReLU(),
                                      nn.Dropout(dropout), nn.Linear(hidden // 2, n_classes))

        def forward(self, x, edge_index, edge_attr, batch):   # edge_attr ignored by SAGE
            h = self.drop(F.relu(self.node_emb(x)))
            for conv, norm in zip(self.convs, self.norms):
                h = self.drop(norm(h + F.relu(conv(h, edge_index))))   # residual + LayerNorm
            h = global_mean_pool(h, batch)
            return self.head(h)                 # [batch, n_classes]

    return {"Graphormer": GraphormerModel, "GraphGPS": GraphGPSModel,
            "GraphSAGE": GraphSAGEModel}


# ----------------------------------------------------------------------------- #
#  Stage 5 — train / evaluate helpers (multiclass)
# ----------------------------------------------------------------------------- #
def evaluate_multiclass(y_true, y_prob, name, class_names):
    from sklearn.metrics import (accuracy_score, f1_score, confusion_matrix,
                                  roc_auc_score)
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_prob).argmax(1)
    try:
        auc = roc_auc_score(y_true, y_prob, multi_class="ovr", average="macro",
                            labels=list(range(len(class_names))))
    except Exception:
        auc = np.nan
    per_class_f1 = f1_score(y_true, y_pred, average=None,
                            labels=list(range(len(class_names))), zero_division=0)
    return {
        "Model": name,
        "Accuracy": round(accuracy_score(y_true, y_pred) * 100, 1),
        "Macro-F1": round(f1_score(y_true, y_pred, average="macro", zero_division=0), 4),
        "Weighted-F1": round(f1_score(y_true, y_pred, average="weighted", zero_division=0), 4),
        "Macro-AUC(ovr)": round(auc, 4) if not np.isnan(auc) else "n/a",
        **{f"F1[{c}]": round(f, 3) for c, f in zip(class_names, per_class_f1)},
        "confusion_matrix": confusion_matrix(
            y_true, y_pred, labels=list(range(len(class_names)))).tolist(),
    }


def train_graph_model(model_kind, models,
                      train_g, val_g, test_g, n_classes, class_weights, device,
                      hidden=GT_HIDDEN, layers=GT_LAYERS):
    """Train one graph model (Graphormer / GraphGPS / GraphSAGE) with early stopping.

    `hidden` / `layers` control model size/depth (smaller = better for small data).
    Pass a uniform `class_weights` to disable class weighting.
    """
    import copy
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch_geometric.loader import DataLoader

    has_pe = (model_kind == "GraphGPS")
    Cls = models[model_kind]
    if model_kind == "Graphormer":
        model = Cls(n_classes, ATOM_DIM, hidden, GT_HEADS, layers, GT_DROPOUT).to(device)
    elif model_kind == "GraphGPS":
        model = Cls(n_classes, ATOM_DIM, hidden, PE_DIM, GT_HEADS, layers, GT_DROPOUT).to(device)
    else:  # GraphSAGE (no attention heads, no positional encoding)
        model = Cls(n_classes, ATOM_DIM, hidden, layers, GT_DROPOUT).to(device)

    opt = torch.optim.Adam(model.parameters(), lr=GT_LR)
    criterion = nn.CrossEntropyLoss(weight=class_weights.to(device))

    tl = DataLoader(train_g, batch_size=BATCH, shuffle=True)
    vl = DataLoader(val_g, batch_size=BATCH, shuffle=False)
    te = DataLoader(test_g, batch_size=BATCH, shuffle=False)

    def _forward(batch):
        if has_pe:
            return model(batch.x, batch.edge_index, batch.edge_attr, batch.batch, batch.pe)
        return model(batch.x, batch.edge_index, batch.edge_attr, batch.batch)

    def _probs(loader):
        model.eval()
        P, Y = [], []
        with torch.no_grad():
            for batch in loader:
                batch = batch.to(device)
                P.append(F.softmax(_forward(batch), dim=1).cpu().numpy())
                Y.append(batch.y.cpu().numpy())
        return np.concatenate(P), np.concatenate(Y)

    from sklearn.metrics import f1_score
    best_state, best_f1, no_improve = None, -1.0, 0
    for epoch in range(1, MAX_EPOCHS + 1):
        model.train()
        for batch in tl:
            batch = batch.to(device)
            opt.zero_grad()
            loss = criterion(_forward(batch), batch.y)
            loss.backward()
            opt.step()
        vp, vy = _probs(vl)
        f1 = f1_score(vy, vp.argmax(1), average="macro", zero_division=0)
        if f1 > best_f1:
            best_f1, best_state, no_improve = f1, copy.deepcopy(model.state_dict()), 0
        else:
            no_improve += 1
        if no_improve >= PATIENCE:
            print(f"    {model_kind}: early stop @ epoch {epoch}, best val macro-F1={best_f1:.4f}")
            break
    if best_state is not None:
        model.load_state_dict(best_state)
    test_prob, test_y = _probs(te)
    return test_prob, test_y


# ----------------------------------------------------------------------------- #
#  Stage 6 — classic ML on fingerprints (RandomForest, XGBoost)
# ----------------------------------------------------------------------------- #
def train_classic(X_tr, y_tr, X_te, which):
    out = {}
    if "RandomForest" in which:
        from sklearn.ensemble import RandomForestClassifier
        rf = RandomForestClassifier(n_estimators=400, class_weight="balanced",
                                    random_state=SEED, n_jobs=-1)
        rf.fit(X_tr, y_tr)
        out["RandomForest"] = rf.predict_proba(X_te)
    if "XGBoost" in which:
        try:
            from xgboost import XGBClassifier
            xgb = XGBClassifier(n_estimators=400, max_depth=6, learning_rate=0.1,
                                subsample=0.8, colsample_bytree=0.8, random_state=SEED,
                                eval_metric="mlogloss", n_jobs=-1)
            xgb.fit(X_tr, y_tr)
            out["XGBoost"] = xgb.predict_proba(X_te)
        except Exception as exc:
            print(f"    [warn] XGBoost skipped: {exc}")
    return out


# ----------------------------------------------------------------------------- #
#  Main
# ----------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(description="Per-marker QSAR (FULL dataset, 3-class)")
    parser.add_argument("--marker", default="ALT", help="Marker to model (e.g. ALT, AST)")
    parser.add_argument("--data", default=None,
                        help="Path to the dataset xlsx (default: DATA_XLSX in the file). "
                             "Set this on the HPC to point at the uploaded dataset.")
    parser.add_argument("--sheet", default=DATA_SHEET, help="Sheet name (default: Findings)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Quick smoke test: keep only N random chemicals "
                             "(e.g. --limit 300) so SMILES + training run fast.")
    parser.add_argument("--test-size", type=float, default=0.20)
    parser.add_argument("--val-size", type=float, default=0.20)
    parser.add_argument("--smiles-sleep", type=float, default=0.2,
                        help="Seconds between PubChem calls")
    parser.add_argument("--models", nargs="+", default=None, choices=ALL_MODELS,
                        help="Subset of models to (re)train, e.g. --models GraphSAGE. "
                             "Default: all. A subset UPDATES those rows in the existing "
                             "results table and keeps the others.")
    # --- experiment knobs (for the GNN small-data investigation) ---
    parser.add_argument("--tag", default="FULL",
                        help="Label for the results filenames (results_<marker>_<tag>.csv). "
                             "Use different tags to compare experiments without overwriting.")
    parser.add_argument("--no-class-weight", action="store_true",
                        help="Disable class weighting for the graph models "
                             "(test if it stops over-predicting the rare class).")
    parser.add_argument("--gt-hidden", type=int, default=GT_HIDDEN,
                        help=f"Graph-model hidden size (default {GT_HIDDEN}; try 64 for small data).")
    parser.add_argument("--gt-layers", type=int, default=GT_LAYERS,
                        help=f"Graph-model depth (default {GT_LAYERS}; try 1-2 for small data).")
    args = parser.parse_args()
    selected = set(args.models) if args.models else set(ALL_MODELS)

    np.random.seed(SEED)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1) labels ---------------------------------------------------------------
    full = build_full_dataset(args.marker, data_path=args.data, sheet=args.sheet)

    if args.limit and args.limit < len(full):
        full = full.sample(n=args.limit, random_state=SEED).reset_index(drop=True)
        print(f"[limit] SMOKE TEST — using {len(full)} random chemicals only")

    # 2) name -> SMILES -------------------------------------------------------
    smi_map = resolve_smiles(full["chemical"].tolist(), sleep=args.smiles_sleep)
    full["smiles"] = full["chemical"].map(smi_map)
    # Keep only non-empty *string* SMILES. NaN is truthy, so bool(NaN)==True would
    # let unresolved names slip past a plain .astype(bool) filter and reach RDKit.
    full = full[full["smiles"].map(lambda s: isinstance(s, str) and s.strip() != "")].copy()

    # 3) canonicalize + drop invalid + dedup ----------------------------------
    full["csmi"] = full["smiles"].map(canonicalize)
    full = full.dropna(subset=["csmi"]).drop_duplicates("csmi").reset_index(drop=True)

    # class encoding (only classes present, in canonical order)
    class_names = [c for c in LABEL_ORDER if c in set(full["label"])]
    cls_to_idx = {c: i for i, c in enumerate(class_names)}
    full["y"] = full["label"].map(cls_to_idx)
    n_classes = len(class_names)
    print(f"\n[ready] {len(full)} usable molecules | classes={class_names}")
    print(full["label"].value_counts().to_string())

    # save the built dataset (tagged, so a --limit smoke test doesn't overwrite the real one)
    cols = ["chemical", "csmi", "label", "y", "support"]
    ds_path = RESULTS_DIR / f"dataset_{args.marker}_{args.tag}.csv"
    full[cols].to_csv(ds_path, index=False)
    print(f"[saved] {ds_path}")

    # also save the high-confidence subset (label supported by >= 2 articles)
    hc = full[full["support"] >= 2]
    hc_path = RESULTS_DIR / f"high_confidence_dataset_{args.marker}_{args.tag}.csv"
    hc[cols].to_csv(hc_path, index=False)
    print(f"[saved] {hc_path}  ({len(hc)} molecules, support>=2)")

    if len(full) < 40:
        print("[warn] very few molecules — GNN results will be unreliable.")

    # 4) split (stratified) ---------------------------------------------------
    from sklearn.model_selection import train_test_split
    idx = np.arange(len(full))
    y = full["y"].values

    def strat_split(indices, labels, size):
        try:
            return train_test_split(indices, test_size=size, stratify=labels,
                                    random_state=SEED)
        except ValueError:      # a class too small to stratify
            return train_test_split(indices, test_size=size, random_state=SEED)

    pool_idx, test_idx = strat_split(idx, y, args.test_size)
    tr_idx, val_idx = strat_split(pool_idx, y[pool_idx], args.val_size)
    print(f"[split] train={len(tr_idx)}  val={len(val_idx)}  test={len(test_idx)}")

    # 5) build graphs ---------------------------------------------------------
    import torch
    from sklearn.utils.class_weight import compute_class_weight
    torch.manual_seed(SEED)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[device] {device}")

    smis = full["csmi"].values
    ys = full["y"].values

    graphs = [mol_to_graph(smis[i], ys[i]) for i in range(len(full))]
    ok = [i for i, g in enumerate(graphs) if g is not None]
    graphs = {i: graphs[i] for i in ok}

    # attach Laplacian PE for the GraphGPS variant
    from torch_geometric.data import Data
    gps_graphs = {}
    for i, g in graphs.items():
        pe = compute_laplacian_pe(g)
        gps_graphs[i] = Data(x=g.x, edge_index=g.edge_index, edge_attr=g.edge_attr,
                             y=g.y, pe=pe)

    def subset(indices, store):
        return [store[i] for i in indices if i in store]

    models = build_models_module()
    y_train = ys[[i for i in tr_idx if i in graphs]]
    if args.no_class_weight:
        class_weights = torch.ones(n_classes, dtype=torch.float)   # uniform = no weighting
    else:
        cw = compute_class_weight("balanced", classes=np.arange(n_classes), y=y_train)
        class_weights = torch.tensor(cw, dtype=torch.float)

    results = []

    print(f"[models] training: {sorted(selected)}")
    print(f"[config] tag={args.tag}  class_weight={not args.no_class_weight}  "
          f"gt_hidden={args.gt_hidden}  gt_layers={args.gt_layers}")

    # 6) graph models (only the selected ones) --------------------------------
    #    GraphSAGE uses the plain `graphs` store (it doesn't need the Laplacian PE).
    for kind, store in [("Graphormer", graphs), ("GraphGPS", gps_graphs),
                        ("GraphSAGE", graphs)]:
        if kind not in selected:
            continue
        print(f"\n[train] {kind} ...")
        tp, ty = train_graph_model(
            kind, models,
            subset(tr_idx, store), subset(val_idx, store), subset(test_idx, store),
            n_classes, class_weights, device,
            hidden=args.gt_hidden, layers=args.gt_layers,
        )
        results.append(evaluate_multiclass(ty, tp, kind, class_names))

    # 7) classic ML on fingerprints (only if selected) ------------------------
    if selected & {"RandomForest", "XGBoost"}:
        print("\n[train] classic ML (Morgan fingerprints) ...")
        fps = {i: morgan_fp(smis[i]) for i in ok}
        fps = {i: f for i, f in fps.items() if f is not None}
        tr_f = [i for i in tr_idx if i in fps]
        te_f = [i for i in test_idx if i in fps]
        X_tr = np.stack([fps[i] for i in tr_f]); y_tr = ys[tr_f]
        X_te = np.stack([fps[i] for i in te_f]); y_te = ys[te_f]
        for name, prob in train_classic(X_tr, y_tr, X_te, selected).items():
            results.append(evaluate_multiclass(y_te, prob, name, class_names))

    # 8) report ---------------------------------------------------------------
    res_df = pd.DataFrame(results)
    show_cols = [c for c in res_df.columns if c != "confusion_matrix"]
    out = RESULTS_DIR / f"results_{args.marker}_{args.tag}.csv"
    conf_path = RESULTS_DIR / f"results_{args.marker}_{args.tag}_confusion.json"

    # If only a subset of models ran, MERGE: update those rows, keep the others.
    partial = args.models is not None and out.exists()
    new_table = res_df[show_cols]
    conf_new = {r["Model"]: r["confusion_matrix"] for r in results}
    if partial:
        old = pd.read_csv(out)
        old = old[~old["Model"].isin(new_table["Model"])]        # drop rows we just retrained
        new_table = pd.concat([old, new_table], ignore_index=True)
        if conf_path.exists():
            conf_old = json.loads(conf_path.read_text())
            conf_old.update(conf_new)                             # update retrained models
            conf_new = conf_old
    # keep a stable model order
    order = {m: i for i, m in enumerate(ALL_MODELS)}
    new_table = new_table.sort_values("Model", key=lambda s: s.map(order)).reset_index(drop=True)

    print("\n" + "=" * 70)
    print(f"RESULTS — marker={args.marker} | FULL dataset | {len(full)} molecules | "
          f"classes={class_names}")
    print("=" * 70)
    print(new_table.to_string(index=False))

    new_table.to_csv(out, index=False)
    conf_path.write_text(json.dumps(conf_new, indent=2))
    print(f"\n[saved] {out}")


if __name__ == "__main__":
    main()
