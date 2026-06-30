"""
Accuracy evaluation helpers for IEEE paper tables.
"""

from collections import Counter


class ExtractionAccuracyEvaluator:
    """Compute precision, recall, F1, and inter-model agreement."""

    @staticmethod
    def precision_recall_f1(true_positives, false_positives, false_negatives):
        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) else 0.0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    @staticmethod
    def field_agreement(predictions_by_model, field):
        """
        Simple agreement score across models for one extracted field.

        predictions_by_model example:
            {"gemini": "mitochondrial ROS", "gpt4": "mitochondrial ROS", "claude": "oxidative stress"}
        """
        values = [value.strip().lower() for value in predictions_by_model.values() if value]
        if not values:
            return 0.0
        counts = Counter(values)
        most_common_count = counts.most_common(1)[0][1]
        return round(most_common_count / len(values), 4)

    def evaluate_against_gold(self, predicted_records, gold_records, key_field="pmid"):
        """
        Compare predicted extractions with a manually labeled gold set.

        Each record should contain boolean flags or labels you want to score.
        """
        gold_map = {row[key_field]: row for row in gold_records}
        tp = fp = fn = 0

        for prediction in predicted_records:
            pmid = prediction[key_field]
            gold = gold_map.get(pmid)
            if not gold:
                continue

            predicted_positive = bool(prediction.get("label"))
            gold_positive = bool(gold.get("label"))

            if predicted_positive and gold_positive:
                tp += 1
            elif predicted_positive and not gold_positive:
                fp += 1
            elif not predicted_positive and gold_positive:
                fn += 1

        metrics = self.precision_recall_f1(tp, fp, fn)
        metrics.update({"true_positives": tp, "false_positives": fp, "false_negatives": fn})
        return metrics

    def build_comparison_table(self, model_results):
        """
        Build an IEEE-friendly summary table.

        model_results example:
            {
              "gemini": {"precision": 0.91, "recall": 0.88, "f1": 0.89},
              "gpt4": {...},
            }
        """
        rows = []
        for model, metrics in model_results.items():
            rows.append(
                {
                    "model": model,
                    "precision": metrics.get("precision", 0),
                    "recall": metrics.get("recall", 0),
                    "f1": metrics.get("f1", 0),
                }
            )
        rows.sort(key=lambda row: row["f1"], reverse=True)
        return rows
