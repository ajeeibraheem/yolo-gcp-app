from __future__ import annotations
import os
from typing import List, Dict

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

def parse_yolo_labels(root: str) -> List[Dict]:
    """
    Walk `root` and return docs: {image_path, labels}
    - image_path is relative to `root`, with forward slashes
    - YOLO labels are discovered with a robust set of candidates:
        * same folder: <image_stem>.txt
        * any 'images' segment mirrored to 'labels'
        * labels/<same/relative/path>.txt
        * labels/train|val|test/<mirrored path>.txt
        * labels/<basename>.txt
    """
    root = os.path.abspath(root)

    def rel(path: str) -> str:
        return os.path.relpath(path, root).replace("\\", "/")

    def stem(path: str) -> str:
        base, _ = os.path.splitext(path)
        return base

    def label_candidates(rel_img: str) -> List[str]:
        """Return ordered, de-duplicated candidate label paths (relative to root)."""
        rel_img = rel_img.lstrip("/")
        parts = rel_img.split("/")
        base_txt = stem(rel_img) + ".txt"

        cands: List[str] = []
        # 1) same folder
        cands.append(base_txt)

        # 2) replace any 'images' segment with 'labels'
        for i, seg in enumerate(parts):
            if seg.lower() == "images":
                repl = parts[:]
                repl[i] = "labels"
                cands.append(stem("/".join(repl)) + ".txt")
                break  # one mirror is enough

        # 3) labels/<same path>.txt
        cands.append("labels/" + stem(rel_img) + ".txt")

        # 4) images/train|val|test/... -> labels/train|val|test/...
        if len(parts) >= 2 and parts[0].lower() == "images" and parts[1].lower() in ("train", "val", "test"):
            mirrored = "labels/" + "/".join(parts[1:-1]) + "/" + os.path.splitext(parts[-1])[0] + ".txt"
            cands.append(mirrored)

        # 5) top-level labels folder with only the basename
        cands.append("labels/" + os.path.splitext(os.path.basename(rel_img))[0] + ".txt")

        # de-dupe preserving order
        seen = set(); out: List[str] = []
        for c in cands:
            c = c.replace("\\", "/")
            if c not in seen:
                seen.add(c); out.append(c)
        return out

    docs: List[Dict] = []
    for dp, _, fns in os.walk(root):
        for fn in fns:
            ext = os.path.splitext(fn.lower())[1]
            if ext not in IMAGE_EXTS:
                continue

            img_abs = os.path.join(dp, fn)
            rel_img = rel(img_abs)
            labels = []

            # try candidates until first label file is found
            for cand in label_candidates(rel_img):
                lp = os.path.join(root, cand)
                if os.path.exists(lp) and os.path.getsize(lp) > 0:
                    with open(lp, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line or line.startswith("#"):
                                continue
                            parts = line.split()
                            if len(parts) < 5:
                                continue
                            class_id, xc, yc, w, h = parts[:5]
                            try:
                                labels.append({
                                    "class_id": int(float(class_id)),
                                    "x_center": float(xc),
                                    "y_center": float(yc),
                                    "width": float(w),
                                    "height": float(h),
                                })
                            except ValueError:
                                continue
                    break  # stop at the first found label file

            docs.append({"image_path": rel_img, "labels": labels})

    return docs
