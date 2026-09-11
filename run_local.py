"""Cross-platform version of run_local.sh: python run_local.py  (Java 17+ and requirements.txt installed)."""
import os, subprocess, sys
root = os.path.dirname(os.path.abspath(__file__))
env = {**os.environ, "REPO_ROOT": root}
steps = ["data_gen/generate.py", "fabric/notebooks/01_bronze_ingest.py", "fabric/notebooks/02_silver_clean.py",
         "fabric/notebooks/03_gold_star_schema.py", "ai_product/train_lead_scorer.py"]
for s in steps:
    print(f"\n=== {s} ===", flush=True)
    subprocess.run([sys.executable, os.path.join(root, s)], env=env, check=True, cwd=root)
print("\ndone — start the app with: streamlit run ai_product/app.py")
