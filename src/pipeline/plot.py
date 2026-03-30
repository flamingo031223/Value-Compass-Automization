import matplotlib.pyplot as plt
import seaborn as sns
import os

def generate_all_plots(data, output_dir="output/plots"):
    os.makedirs(output_dir, exist_ok=True)

    for name, df in data.items():
        if "model" not in df.columns:
            continue

        plt.figure(figsize=(12,6))
        df_plot = df.set_index("model")

        df_plot.T.plot(kind="bar")
        plt.title(f"{name} Benchmark")
        plt.tight_layout()

        plt.savefig(f"{output_dir}/{name}.png")
        plt.close()
