import json
import glob
import os
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt


SAVE_DIR = "./manual-evaluations/patient-matching/"

eval_files = glob.glob(os.path.join(SAVE_DIR, "manual_eval_*.json"))

print(f"Found {len(eval_files)} evaluation files.")

models = {}

for fpath in eval_files:
    fname = os.path.basename(fpath)

    core = fname.replace("manual_eval_", "").replace(".json", "")

    if "_patient-" in core:
        exp_name, patient = core.split("_patient-")
    else:
        exp_name = core
        patient = "unknown"

    if "-experiment" in exp_name:
        model = exp_name.split("-experiment")[0]
    else:
        model = exp_name

    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)

    metrics = data["metrics"]
    correct = metrics["correct"]
    partial = metrics["partial"]
    wrong = metrics["wrong"]
    total = metrics["total"]

    if model not in models:
        models[model] = {
            "total_fields": 0,
            "correct": 0,
            "partial": 0,
            "wrong": 0,
            "per_patient": []
        }

    m = models[model]
    m["total_fields"] += total
    m["correct"] += correct
    m["partial"] += partial
    m["wrong"] += wrong

    m["per_patient"].append({
        "patient": patient,
        "correct": correct,
        "partial": partial,
        "wrong": wrong,
        "human_accuracy": metrics["human_accuracy"],
        "partial_score": metrics["partial_score"]
    })

for model, agg in models.items():
    total_fields = agg["total_fields"]
    correct = agg["correct"]
    partial = agg["partial"]
    wrong = agg["wrong"]

    global_accuracy = correct / total_fields * 100 if total_fields else 0.0
    global_partial_score = (correct + 0.5 * partial) / total_fields * 100 if total_fields else 0.0

    agg["global_accuracy"] = global_accuracy
    agg["global_partial_score"] = global_partial_score

    print(f"\n=== RESULTS FOR MODEL: {model} ===")
    print(f"Total criteria evaluated: {total_fields}")
    print(f"Correct: {correct}")
    print(f"Partial: {partial}")
    print(f"Wrong: {wrong}")
    print(f"Global human accuracy: {global_accuracy:.2f}%")
    print(f"Global partial-aware score: {global_partial_score:.2f}%")

save_path = os.path.join(SAVE_DIR, "AGGREGATED_RESULTS_BY_MODEL.json")

with open(save_path, "w", encoding="utf-8") as f:
    json.dump(models, f, indent=4, ensure_ascii=False)

print(f"\nSaved aggregated results by model to {save_path}")

PLOTS_DIR = "./manual-evaluations/patient-matching/plots"
os.makedirs(PLOTS_DIR, exist_ok=True)

AGG_PATH = os.path.join(SAVE_DIR, "AGGREGATED_RESULTS_BY_MODEL.json")

with open(AGG_PATH, "r", encoding="utf-8") as f:
    aggregated = json.load(f)

rows = []
for model, data in aggregated.items():
    for p in data["per_patient"]:
        rows.append({
            "model": model,
            "patient": p["patient"],
            "accuracy": p["human_accuracy"]
        })

df = pd.DataFrame(rows)

pivot = df.pivot(index="patient", columns="model", values="accuracy")

plt.figure(figsize=(12, 8))
sns.heatmap(pivot, annot=True, cmap="viridis", fmt=".1f")
plt.title("Patient–Trial Matching Accuracy per Patient and Model")
plt.xlabel("Model")
plt.ylabel("Patient")
plt.tight_layout()
plt.savefig(f"{PLOTS_DIR}/patient_matching_heatmap.png", dpi=300)
plt.close()

print("Saved heatmap to:", f"{PLOTS_DIR}/patient_matching_heatmap.png")

global_rows = []
for model, data in aggregated.items():
    global_rows.append({
        "model": model,
        "accuracy": data["global_accuracy"],
        "partial_score": data["global_partial_score"]
    })

df_global = pd.DataFrame(global_rows)

plt.figure(figsize=(8, 5))
sns.barplot(data=df_global, x="model", y="accuracy", palette="crest")
plt.title("Global Accuracy by Model – Patient–Trial Matching")
plt.ylabel("Accuracy (%)")
plt.xlabel("Model")
plt.ylim(0, 100)
plt.tight_layout()
plt.savefig(f"{PLOTS_DIR}/patient_matching_global_accuracy.png", dpi=300)
plt.close()

print("Saved global accuracy bar chart to:", f"{PLOTS_DIR}/patient_matching_global_accuracy.png")

dist_rows = []
for model, data in aggregated.items():
    dist_rows.append({
        "model": model,
        "correct": data["correct"],
        "wrong": data["wrong"]
    })

df_dist = pd.DataFrame(dist_rows)
df_dist_long = df_dist.melt(id_vars="model", value_vars=["correct", "wrong"],
                            var_name="type", value_name="count")

plt.figure(figsize=(8, 5))
sns.barplot(data=df_dist_long, x="model", y="count", hue="type", palette="Set2")
plt.title("Correct vs Wrong Assignments per Model")
plt.ylabel("Count")
plt.xlabel("Model")
plt.tight_layout()
plt.savefig(f"{PLOTS_DIR}/patient_matching_correct_wrong.png", dpi=300)
plt.close()

print("Saved correct/wrong distribution chart to:", f"{PLOTS_DIR}/patient_matching_correct_wrong.png")
