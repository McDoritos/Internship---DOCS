import json
import glob
import os
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np

AGGREGATED_PATH = "./manual-evaluations/parameter-extraction/AGGREGATED_RESULTS_BY_MODEL.json"
MANUAL_EVAL_DIR = "./manual-evaluations/parameter-extraction/"
SCHEMA_PATH = "../Test_Files/Schemas/parameter-extraction_schema.json"
PLOTS_SAVE_DIR = "./manual-evaluations/parameter-extraction/plots"

# Load aggregated results
with open(AGGREGATED_PATH, "r", encoding="utf-8") as f:
    aggregated = json.load(f)

# Load schema (to compute compliance)
with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
    schema = json.load(f)

schema_fields = set(schema.keys())

# Load all manual evaluation files
manual_files = glob.glob(os.path.join(MANUAL_EVAL_DIR, "manual_eval_*.json"))

print(f"Found {len(manual_files)} manual evaluation files.")

# Temporary structure to accumulate per-model metrics
per_model_extra = {}

for fpath in manual_files:
    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)

    diary = data["diary"]
    manual_results = data["manual_results"]

    # Extract model name from filename
    fname = os.path.basename(fpath)
    core = fname.replace("manual_eval_", "").replace(".json", "")
    exp_name, _ = core.rsplit("_", 1)

    if "-experiment" in exp_name:
        model = exp_name.split("-experiment")[0]
    else:
        model = "deepseek-r1-8b"

    # Compute schema compliance
    predicted_fields = set(manual_results.keys())
    matched = predicted_fields & schema_fields
    schema_compliance_rate = len(matched) / len(schema_fields) * 100

    # Compute missing field rate
    missing_fields = sum(1 for k, v in manual_results.items() if v in ["n", None, "", "null"])
    missing_field_rate = missing_fields / len(manual_results) * 100

    # Store per-model
    if model not in per_model_extra:
        per_model_extra[model] = {
            "schema_compliance_sum": 0,
            "missing_field_rate_sum": 0,
            "count": 0,
            "per_diary": {}
        }

    per_model_extra[model]["schema_compliance_sum"] += schema_compliance_rate
    per_model_extra[model]["missing_field_rate_sum"] += missing_field_rate
    per_model_extra[model]["count"] += 1

    per_model_extra[model]["per_diary"][diary] = {
        "schema_compliance_rate": schema_compliance_rate,
        "missing_field_rate": missing_field_rate
    }

# Merge into aggregated results
for model, extra in per_model_extra.items():
    if model not in aggregated:
        continue

    count = extra["count"]

    aggregated[model]["schema_compliance_rate"] = extra["schema_compliance_sum"] / count
    aggregated[model]["missing_field_rate"] = extra["missing_field_rate_sum"] / count
    aggregated[model]["per_diary_extra"] = extra["per_diary"]

# Save updated aggregated file
with open(AGGREGATED_PATH, "w", encoding="utf-8") as f:
    json.dump(aggregated, f, indent=4, ensure_ascii=False)

print("\nUpdated aggregated results with schema_compliance_rate and missing_field_rate.")

# Ensure plot directory exists
os.makedirs(PLOTS_SAVE_DIR, exist_ok=True)

rows = []
for model, extra in per_model_extra.items():
    rows.append({
        "model": model,
        "schema_compliance_rate": aggregated[model]["schema_compliance_rate"],
        "missing_field_rate": aggregated[model]["missing_field_rate"]
    })

df_extra = pd.DataFrame(rows)

plt.figure(figsize=(10,6))
sns.barplot(data=df_extra, x="schema_compliance_rate", y="model", palette="crest")
plt.title("Schema compliance rate by model")
plt.xlabel("Schema compliance (%)")
plt.ylabel("Model")
plt.tight_layout()

plt.savefig(f"{PLOTS_SAVE_DIR}/schema_compliance_by_model.png", dpi=300)
plt.show()


plt.figure(figsize=(10,6))
sns.barplot(data=df_extra, x="missing_field_rate", y="model", palette="flare")
plt.title("Missing field rate by model")
plt.xlabel("Missing field rate (%)")
plt.ylabel("Model")
plt.tight_layout()

plt.savefig(f"{PLOTS_SAVE_DIR}/missing_field_rate_by_model.png", dpi=300)
plt.show()

rows_cpw = []
for model, agg in aggregated.items():
    if "per_field" not in agg:
        continue
    for field, stats in agg["per_field"].items():
        
        if field == "control":
            continue

        rows_cpw.append({
            "model": model,
            "field": field,
            "correct": stats["correct"],
            "partial": stats["partial"],
            "wrong": stats["wrong"]
        })

df_cpw = pd.DataFrame(rows_cpw)

df_long = df_cpw.melt(
    id_vars=["model", "field"],
    value_vars=["correct", "partial", "wrong"],
    var_name="classification",
    value_name="count"
)

g = sns.catplot(
    data=df_long,
    kind="bar",
    x="field",
    y="count",
    hue="classification",
    col="model",
    col_wrap=1,
    height=5,
    aspect=2,
    palette="Set2"
)

g.set_titles("Model: {col_name}")
g.set_axis_labels("Field", "Count")
g.fig.suptitle("Correct / Partial / Wrong per field across models (without 'control')", y=1.02)

for ax in g.axes.flatten():
    ax.tick_params(axis='x', rotation=45)

plt.tight_layout()

plt.savefig(f"{PLOTS_SAVE_DIR}/correct_partial_wrong_by_field_and_model_no_control.png", dpi=300)
plt.show()

with open(AGGREGATED_PATH, "r", encoding="utf-8") as f:
    aggregated = json.load(f)

model_names = list(aggregated.keys())
accuracies = [aggregated[m]["global_accuracy"] for m in model_names]
partial_scores = [aggregated[m]["global_partial_score"] for m in model_names]

x = np.arange(len(model_names))
width = 0.35

plt.figure(figsize=(10, 6))
plt.bar(x - width/2, accuracies, width, label="Accuracy (%)", color="#1f77b4")
plt.bar(x + width/2, partial_scores, width, label="Partial-aware score (%)", color="#9467bd")

plt.xticks(x, model_names, rotation=20)
plt.ylabel("Score (%)")
plt.ylim(0, 105)
plt.title("Parameter Extraction – Global Accuracy vs Partial-aware Score")
plt.legend()
plt.tight_layout()

# Save plot
plt.savefig(f"{PLOTS_SAVE_DIR}/parameter_extraction_accuracy_vs_partial_score.png", dpi=300)
plt.close()

print(f"Saved accuracy/partial-aware plot to {PLOTS_SAVE_DIR}")