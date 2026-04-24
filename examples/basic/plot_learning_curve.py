import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("server_output/learning_curve.csv")

plt.plot(df["round"], df["accuracy"], marker="o", label="Accuracy")
plt.xlabel("Round")
plt.ylabel("Metric")
plt.title("Learning Curve")
plt.legend()
plt.grid(True)
plt.show()