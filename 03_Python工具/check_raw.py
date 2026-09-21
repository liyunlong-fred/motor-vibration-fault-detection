import numpy as np, glob, os

RAW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "04_数据集", "raw")
p = max(glob.glob(os.path.join(RAW, "*.csv")), key=os.path.getmtime)
raw = np.loadtxt(p, comments="#", dtype=np.int16)

print("文件:", p)
print("样本数 %d  最小 %d  最大 %d  均值 %.1f" % (raw.size, raw.min(), raw.max(), raw.mean()))
print("负样本 %d 个 (%.1f%%)   等于0: %d 个" % ((raw < 0).sum(), 100.0*(raw < 0).mean(), (raw == 0).sum()))
print("前 40 个原始计数:", raw[:40].tolist())