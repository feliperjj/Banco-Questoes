from io import BytesIO
import hashlib
import json

import pytest
from PIL import Image

from src.models.ia_dataset import assess_training_readiness, export_dataset, record_reviewed_example, validate_export


def image_bytes(color="red"):
    stream = BytesIO()
    Image.new("RGB", (8, 8), color).save(stream, format="PNG")
    return stream.getvalue()


def source(value="a"):
    return hashlib.sha256(value.encode()).hexdigest()


def add(root, group="g1", source_value="a", text="texto", color="red"):
    return record_reviewed_example(image_bytes=image_bytes(color), source_sha256=source(source_value), group_id=group, page=1, bounds=(1, 2, 3, 4), text=text, reviewer="ana", confirmed=True, dataset_dir=root)


def test_record_requires_human_confirmation_and_safe_values(tmp_path):
    with pytest.raises(ValueError):
        add(tmp_path, text="")
    with pytest.raises(ValueError):
        record_reviewed_example(image_bytes=image_bytes(), source_sha256="x", group_id="g", page=1, bounds=(1, 2, 3, 4), text="x", reviewer="ana", confirmed=False, dataset_dir=tmp_path)
    path = add(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["origin"] == "human_confirmed"
    assert data["target"] == {"encontrado": True, "texto": "texto"}
    negative = record_reviewed_example(image_bytes=image_bytes(), source_sha256=source("negative"), group_id="g", page=1, bounds=(1, 2, 3, 4), text="", reviewer="ana", confirmed=True, found=False, dataset_dir=tmp_path)
    assert json.loads(negative.read_text(encoding="utf-8"))["target"] == {"encontrado": False, "texto": ""}
    with pytest.raises(ValueError):
        record_reviewed_example(image_bytes=image_bytes(), source_sha256=source("bad-negative"), group_id="g", page=1, bounds=(1, 2, 3, 4), text="texto", reviewer="ana", confirmed=True, found=False, dataset_dir=tmp_path)


def test_export_dedup_and_explicit_holdout_without_leakage(tmp_path):
    dataset, output = tmp_path / "dataset", tmp_path / "out"
    add(dataset, "train", "a", color="red")
    add(dataset, "hold", "b", color="blue")
    add(dataset, "hold", "b", color="blue")
    result = export_dataset(dataset, output, holdout_groups=["hold"])
    assert result["manifest"]["deduplicated"] == 1
    train = [json.loads(line) for line in (output / "train.jsonl").read_text().splitlines()]
    valid = [json.loads(line) for line in (output / "validation.jsonl").read_text().splitlines()]
    assert len(train) == 1 and len(valid) == 1
    assert result["readiness"]["training_ready"] is False
    assert result["readiness"]["train_examples"] == 1


def test_transitive_group_connection_never_crosses_split(tmp_path):
    # A shares source with B, and B shares group with C: all form one component.
    add(tmp_path, "a", "same", "a", "red")
    add(tmp_path, "b", "same", "b", "blue")
    add(tmp_path, "b", "other", "c", "green")
    add(tmp_path, "independent", "independent", "d", "yellow")
    result = export_dataset(tmp_path, tmp_path / "out", holdout_groups=["a"])
    train_groups = {r["group_id"] for r in result["train"]}
    validation_groups = {r["group_id"] for r in result["validation"]}
    assert {"a", "b"}.issubset(validation_groups)
    assert train_groups.isdisjoint(validation_groups)
    assert {r["source_sha256"] for r in result["train"]}.isdisjoint({r["source_sha256"] for r in result["validation"]})


def test_equal_pixels_from_distinct_sources_stay_in_one_split(tmp_path):
    add(tmp_path, "hold", "first", "same label", "red")
    add(tmp_path, "other", "second", "same label", "red")
    result = export_dataset(tmp_path, tmp_path / "out", holdout_groups=["hold"])
    assert result["manifest"]["count"] == 1
    assert set(result["manifest"]["groups"]) == {"hold", "other"}
    assert set(result["manifest"]["source_hashes"]) == {source("first"), source("second")}
    assert set(result["manifest"]["splits"]["validation"]["group_ids"]) == {"hold", "other"}
    assert not result["train"] or not result["validation"]


def test_readiness_rejects_split_overlap():
    record = {"group_id": "g", "source_sha256": "s"}
    result = assess_training_readiness([record], {"train": [record], "validation": [record]}, hardware={"gpu_detected": False})
    assert result["dataset_ready"] is False
    assert any("vazamento" in reason for reason in result["reasons"])


def test_export_snapshot_survives_original_mutation_and_detects_tampering(tmp_path):
    dataset, output = tmp_path / "dataset", tmp_path / "out"
    add(dataset)
    export_dataset(dataset, output)
    original = next(dataset.glob("*.png"))
    original.unlink()
    assert validate_export(output)["valid"] is True
    snapshot = next((output / "images").glob("*.png"))
    snapshot.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash da imagem"):
        validate_export(output)


def test_export_rejects_image_tampering(tmp_path):
    path = add(tmp_path)
    item = json.loads(path.read_text())
    (tmp_path / item["image"]).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="imagem"):
        export_dataset(tmp_path, tmp_path / "out")


def test_bounds_allow_zero_but_reject_inverted(tmp_path):
    record_reviewed_example(image_bytes=image_bytes(), source_sha256=source(), group_id="g", page=1, bounds=(0, 0, 3, 4), text="x", reviewer="ana", confirmed=True, dataset_dir=tmp_path)
    with pytest.raises(ValueError):
        record_reviewed_example(image_bytes=image_bytes(), source_sha256=source("b"), group_id="g", page=1, bounds=(3, 0, 1, 4), text="x", reviewer="ana", confirmed=True, dataset_dir=tmp_path)


def test_unknown_holdout_and_conflicting_label_are_rejected(tmp_path):
    path = add(tmp_path)
    with pytest.raises(ValueError, match="desconhecidos"):
        export_dataset(tmp_path, tmp_path / "out", holdout_groups=["missing"])
    item = json.loads(path.read_text())
    item["target"]["texto"] = "outro"
    path.write_text(json.dumps(item), encoding="utf-8")
    with pytest.raises(ValueError, match="label"):
        export_dataset(tmp_path, tmp_path / "out2")

