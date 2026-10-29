"""Dataset local de exemplos de transcrição conferidos por uma pessoa.

Este módulo somente registra e exporta dados. Ele não chama modelos, não
infere aprovação humana e não inicia treinamento.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import uuid
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import unquote, urlparse

from PIL import Image

from src.config import DATA_DIR

_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_MIN_EXAMPLES = 100
_MIN_GROUPS = 5
_PROMPT = "Transcreva exatamente o texto encontrado no recorte, sem inventar conteúdo."


def _record_sources(record: dict[str, Any]) -> set[str]:
    return set(record.get("_source_hashes", [record.get("source_sha256")]))


def _record_groups(record: dict[str, Any]) -> set[str]:
    return set(record.get("_group_ids", [record.get("group_id")]))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _valid_sha(value: str, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{label} deve ser um SHA-256 hexadecimal válido")
    return value.lower()


def _safe_component(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value in {".", ".."}:
        raise ValueError(f"{label} não pode ser vazio")
    if Path(value).name != value or "\\" in value or "/" in value:
        raise ValueError(f"{label} contém caminho inválido")
    return value.strip()


def _validate_image(data: bytes) -> bytes:
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise ValueError("image_bytes deve conter bytes de uma imagem")
    try:
        from io import BytesIO
        with Image.open(BytesIO(data)) as image:
            if image.format not in {"PNG", "JPEG"}:
                raise ValueError("a imagem deve ser PNG ou JPEG")
            image.verify()
        with Image.open(BytesIO(data)) as image:
            image.load()
            output = BytesIO()
            image.convert("RGBA").save(output, format="PNG")
            return output.getvalue()
    except (OSError, SyntaxError) as exc:
        raise ValueError("image_bytes não contém PNG/JPEG válido") from exc


def _validate_bounds(bounds: Sequence[float]) -> list[float]:
    if isinstance(bounds, (str, bytes)) or not isinstance(bounds, Sequence) or len(bounds) != 4:
        raise ValueError("bounds deve ser uma sequência com quatro números")
    result: list[float] = []
    for item in bounds:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError("bounds deve conter números finitos positivos")
        number = float(item)
        if not math.isfinite(number) or number < 0:
            raise ValueError("bounds deve conter números finitos não negativos")
        result.append(number)
    if not result[0] < result[2] or not result[1] < result[3]:
        raise ValueError("bounds deve representar x0<x1 e y0<y1")
    return result


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def record_reviewed_example(
    *, image_bytes: bytes, source_sha256: str, group_id: str, page: int,
    bounds: Sequence[float], text: str, reviewer: str, confirmed: bool,
    found: bool = True,
    dataset_dir: Path | None = None,
) -> Path:
    """Persist one explicitly human-confirmed example and return its JSON path."""
    if confirmed is not True:
        raise ValueError("o exemplo só pode ser registrado com confirmed=True")
    source_sha256 = _valid_sha(source_sha256, "source_sha256")
    group_id = _safe_component(group_id, "group_id")
    reviewer = reviewer.strip() if isinstance(reviewer, str) else ""
    if not reviewer:
        raise ValueError("reviewer não pode ser vazio")
    if isinstance(page, bool) or not isinstance(page, int) or page <= 0:
        raise ValueError("page deve ser um inteiro positivo")
    if type(found) is not bool:
        raise ValueError("found deve ser booleano")
    if not isinstance(text, str) or (found and not text.strip()) or (not found and text != ""):
        raise ValueError("text incompatível com found")
    normalized_bounds = _validate_bounds(bounds)
    png_bytes = _validate_image(image_bytes)

    root = Path(dataset_dir) if dataset_dir is not None else DATA_DIR / "ia_local" / "exemplos"
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    item_id = uuid.uuid4().hex
    image_name = f"{item_id}.png"
    json_path = root / f"{item_id}.json"
    image_path = root / image_name
    record = {
        "schema_version": 1,
        "id": item_id,
        "image": image_name,
        "image_sha256": _sha256(png_bytes),
        "source_sha256": source_sha256,
        "origin": "human_confirmed",
        "group_id": group_id,
        "page": page,
        "bounds": normalized_bounds,
        "text": text,
        "reviewer": reviewer,
        "confirmed": True,
        "prompt": _PROMPT,
        "target": {"encontrado": found, "texto": text},
    }
    _atomic_write(image_path, png_bytes)
    _atomic_write(json_path, (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    return json_path


def _read_records(dataset_dir: Path) -> list[dict[str, Any]]:
    root = Path(dataset_dir).resolve()
    if not root.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        if path.name in {"manifest.json", "readiness.json"}:
            continue
        if not path.resolve().is_relative_to(root):
            raise ValueError(f"registro fora do dataset: {path.name}")
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"registro inválido: {path.name}") from exc
        if not isinstance(item, dict):
            raise ValueError(f"registro inválido: {path.name}")
        if item.get("schema_version") != 1 or type(item.get("confirmed")) is not bool or item.get("confirmed") is not True or item.get("origin") != "human_confirmed":
            raise ValueError(f"registro sem confirmação humana: {path.name}")
        image_name = item.get("image")
        if not isinstance(image_name, str) or Path(image_name).name != image_name:
            raise ValueError(f"caminho de imagem inválido: {path.name}")
        image_path = root / image_name
        if not image_path.resolve().is_relative_to(root):
            raise ValueError(f"imagem fora do dataset: {image_name}")
        try:
            image_bytes = image_path.read_bytes()
            normalized = _validate_image(image_bytes)
        except (OSError, ValueError) as exc:
            raise ValueError(f"imagem inválida ou adulterada: {image_name}") from exc
        if _sha256(image_bytes) != item.get("image_sha256"):
            raise ValueError(f"hash da imagem não confere: {image_name}")
        # The exported image must remain valid as stored, without rewriting it.
        item = dict(item)
        item["_path"] = image_path
        item["_image_bytes"] = image_bytes
        item["_normalized_png_sha256"] = _sha256(normalized)
        _valid_sha(item.get("source_sha256"), "source_sha256")
        if not isinstance(item.get("reviewer"), str) or not item["reviewer"].strip():
            raise ValueError(f"reviewer inválido: {path.name}")
        if isinstance(item.get("page"), bool) or not isinstance(item.get("page"), int) or item["page"] <= 0:
            raise ValueError(f"página inválida: {path.name}")
        _validate_bounds(item.get("bounds"))
        _safe_component(item.get("group_id"), "group_id")
        if not item.get("group_id") or not isinstance(item.get("text"), str):
            raise ValueError(f"metadados incompletos: {path.name}")
        target = item.get("target")
        if (not isinstance(target, dict) or set(target) != {"encontrado", "texto"}
                or type(target.get("encontrado")) is not bool
                or not isinstance(target.get("texto"), str) or target["texto"] != item["text"]
                or (target["encontrado"] and not target["texto"].strip())
                or (not target["encontrado"] and target["texto"] != "")):
            raise ValueError(f"label incompatível com texto conferido: {path.name}")
        records.append(item)
    return records


def _components(records: list[dict[str, Any]]) -> list[list[int]]:
    parent = list(range(len(records)))
    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value
    def union(left: int, right: int) -> None:
        left, right = find(left), find(right)
        if left != right:
            parent[right] = left
    owners: dict[tuple[str, str], int] = {}
    for index, record in enumerate(records):
        for key in [("source", value.lower()) for value in record.get("_source_hashes", [record["source_sha256"]])]:
            owners.setdefault(key, index)
            if owners[key] != index:
                union(index, owners[key])
        for key in [("group", value) for value in record.get("_group_ids", [record["group_id"]])] + [("image", record["image_sha256"])]:
            if key in owners:
                union(index, owners[key])
            else:
                owners[key] = index
    grouped: dict[int, list[int]] = {}
    for index in range(len(records)):
        grouped.setdefault(find(index), []).append(index)
    # UUIDs identify arquivos, mas não devem decidir o split: recriar o mesmo
    # dataset precisa produzir a mesma separação.
    return sorted(grouped.values(), key=lambda indexes: min(
        (records[i]["source_sha256"].lower(), records[i]["group_id"], records[i]["text"])
        for i in indexes
    ))


def assess_training_readiness(records: Iterable[dict[str, Any]], splits: dict[str, Any], hardware: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return conservative readiness evidence; this function never estimates training time."""
    records = list(records)
    train = list(splits.get("train", []))
    validation = list(splits.get("validation", []))
    groups = {group for r in records for group in _record_groups(r)}
    reasons: list[str] = []
    train_sources = {source for r in train for source in _record_sources(r)}
    validation_sources = {source for r in validation for source in _record_sources(r)}
    train_groups = {group for r in train for group in _record_groups(r)}
    validation_groups = {group for r in validation for group in _record_groups(r)}
    dataset_ready = True
    if len(records) < _MIN_EXAMPLES or len(groups) < _MIN_GROUPS:
        reasons.append(f"dataset pequeno: requer pelo menos {_MIN_EXAMPLES} exemplos e {_MIN_GROUPS} grupos (não é garantia de precisão)")
        dataset_ready = False
    if not train:
        reasons.append("treino vazio")
        dataset_ready = False
    if not validation:
        reasons.append("sem validação independente")
        dataset_ready = False
    if train_sources & validation_sources or train_groups & validation_groups:
        reasons.append("vazamento de source_sha256 ou group_id entre treino e validação")
        dataset_ready = False
    gpu_value = (hardware or {}).get("gpu_detected") if hardware is not None else None
    hardware_pending = hardware is None
    if hardware_pending:
        hardware_status = "não avaliado"
    else:
        hardware_status = "gpu_detectada" if gpu_value is True else "gpu_nao_detectada_cpu_possivel"
    return {"dataset_ready": dataset_ready, "training_ready": dataset_ready and not hardware_pending, "hardware_pending": hardware_pending, "hardware_status": hardware_status, "reasons": reasons, "examples": len(records), "groups": len(groups), "train_examples": len(train), "validation_examples": len(validation), "gpu_detected": gpu_value}


def export_dataset(dataset_dir: Path, output_dir: Path, *, holdout_groups: Iterable[str] | None = None) -> dict[str, Any]:
    records = _read_records(Path(dataset_dir))
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    image_output = output / "images"
    image_output.mkdir(parents=True, exist_ok=True)
    seen: set[tuple[str, str, str]] = set()
    labels_by_image: dict[str, str] = {}
    unique: list[dict[str, Any]] = []
    for record in records:
        target_json = json.dumps(record["target"], ensure_ascii=False, sort_keys=True)
        key = (record["image_sha256"], target_json)
        image_key = record["image_sha256"]
        if image_key in labels_by_image and labels_by_image[image_key] != target_json:
            raise ValueError("labels conflitantes para a mesma imagem")
        labels_by_image[image_key] = target_json
        if key not in seen:
            record = dict(record)
            record["_group_ids"] = [record["group_id"]]
            record["_source_hashes"] = [record["source_sha256"]]
            seen.add(key)
            unique.append(record)
        else:
            representative = unique[next(i for i, item in enumerate(unique) if (item["image_sha256"], json.dumps(item["target"], ensure_ascii=False, sort_keys=True)) == key)]
            representative.setdefault("_group_ids", [representative["group_id"]]).append(record["group_id"])
            representative.setdefault("_source_hashes", [representative["source_sha256"]]).append(record["source_sha256"])
    components = _components(unique)
    explicit = set(holdout_groups or ())
    known_groups = {group for record in unique for group in _record_groups(record)}
    unknown_groups = explicit - known_groups
    if unknown_groups:
        raise ValueError(f"holdout_groups desconhecidos: {', '.join(sorted(unknown_groups))}")
    validation_indexes: set[int] = set()
    for component_number, indexes in enumerate(components):
        component_groups = {group for i in indexes for group in _record_groups(unique[i])}
        if explicit & component_groups:
            validation_indexes.update(indexes)
        elif not explicit and len(components) > 1 and component_number % 5 == 0:
            validation_indexes.update(indexes)
    # A sole group is kept entirely in training by default. An explicitly
    # requested holdout remains authoritative even when it leaves no training
    # examples; it is not an invented split.
    if len(components) <= 1 and not explicit:
        validation_indexes.clear()
    train = [r for i, r in enumerate(unique) if i not in validation_indexes]
    validation = [r for i, r in enumerate(unique) if i in validation_indexes]

    split_hashes: dict[str, str] = {}
    split_images: dict[str, list[dict[str, Any]]] = {}
    def write_jsonl(name: str, values: list[dict[str, Any]]) -> None:
        lines = []
        image_metadata: list[dict[str, Any]] = []
        for record in values:
            snapshot_name = f"{record['image_sha256']}.png"
            snapshot_path = image_output / snapshot_name
            image_bytes = record["_image_bytes"]
            if snapshot_path.exists():
                if not snapshot_path.is_file() or _sha256(snapshot_path.read_bytes()) != record["image_sha256"]:
                    raise ValueError(f"snapshot de imagem adulterado: {snapshot_name}")
            else:
                _atomic_write(snapshot_path, image_bytes)
            relative_image = Path("images") / snapshot_name
            image_metadata.append({"id": record["id"], "sha256": record["image_sha256"], "size": len(image_bytes), "path": relative_image.as_posix()})
            lines.append(json.dumps({"messages": [{"role": "system", "content": _PROMPT}, {"role": "user", "content": [{"type": "image_url", "image_url": {"url": snapshot_path.as_uri()}}, {"type": "text", "text": _PROMPT}]}, {"role": "assistant", "content": json.dumps(record["target"], ensure_ascii=False, sort_keys=True)}]}, ensure_ascii=False))
        payload = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
        _atomic_write(output / name, payload)
        split_hashes[name] = _sha256(payload)
        split_images[name.removesuffix(".jsonl")] = image_metadata
    write_jsonl("train.jsonl", train)
    write_jsonl("validation.jsonl", validation)
    readiness = assess_training_readiness(unique, {"train": train, "validation": validation})
    def split_metadata(values: list[dict[str, Any]]) -> dict[str, Any]:
        return {"ids": [r["id"] for r in values], "source_hashes": sorted({source for r in values for source in _record_sources(r)}), "group_ids": sorted({group for r in values for group in _record_groups(r)})}
    manifest = {"schema_version": 1, "count": len(unique), "deduplicated": len(records) - len(unique), "train_count": len(train), "validation_count": len(validation), "source_hashes": sorted({source for r in unique for source in _record_sources(r)}), "groups": sorted({group for r in unique for group in _record_groups(r)}), "holdout_groups": sorted(explicit), "splits": {"train": split_metadata(train), "validation": split_metadata(validation)}, "images": split_images, "jsonl_sha256": split_hashes, "human_confirmed_only": True, "automatic_training": False}
    _atomic_write(output / "manifest.json", (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    _atomic_write(output / "readiness.json", (json.dumps(readiness, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return {"train": train, "validation": validation, "manifest": manifest, "readiness": readiness, "output_dir": output}


def _local_file_url(url: str) -> Path:
    parsed = urlparse(url)
    if parsed.scheme != "file":
        raise ValueError("referência de imagem não é um file URL")
    value = unquote(parsed.path)
    if parsed.netloc:
        value = f"//{parsed.netloc}{value}"
    if re.match(r"^/[A-Za-z]:/", value):
        value = value[1:]
    return Path(value)


def validate_export(output_dir: Path) -> dict[str, Any]:
    """Revalidate an exported immutable snapshot before any future trainer uses it."""
    root = Path(output_dir).resolve()
    manifest_path = root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("manifest do export inválido") from exc
    image_root = (root / "images").resolve()
    references: list[dict[str, Any]] = []
    for name in ("train.jsonl", "validation.jsonl"):
        path = root / name
        payload = path.read_bytes()
        if _sha256(payload) != manifest.get("jsonl_sha256", {}).get(name):
            raise ValueError(f"hash JSONL não confere: {name}")
        for line in payload.decode("utf-8").splitlines():
            item = json.loads(line)
            try:
                image_url = item["messages"][1]["content"][0]["image_url"]["url"]
            except (KeyError, IndexError, TypeError) as exc:
                raise ValueError(f"schema multimodal inválido: {name}") from exc
            image_path = _local_file_url(image_url)
            if not image_path.resolve().is_relative_to(image_root) or image_path.is_symlink():
                raise ValueError("referência de imagem fora do snapshot")
            data = image_path.read_bytes()
            image_sha = _sha256(data)
            if image_path.suffix.lower() != ".png" or image_sha != image_path.stem:
                raise ValueError(f"hash da imagem não confere: {image_path.name}")
            references.append({"split": name.removesuffix(".jsonl"), "path": image_path.relative_to(root).as_posix(), "sha256": image_sha, "size": len(data)})
    expected = [entry for values in manifest.get("images", {}).values() for entry in values]
    expected_keys = {(entry["path"], entry["sha256"], entry["size"]) for entry in expected}
    actual_keys = {(entry["path"], entry["sha256"], entry["size"]) for entry in references}
    if not actual_keys.issubset(expected_keys):
        raise ValueError("manifest não cobre todas as imagens referenciadas")
    train_images = {entry["sha256"] for entry in references if entry["split"] == "train"}
    validation_images = {entry["sha256"] for entry in references if entry["split"] == "validation"}
    if train_images & validation_images:
        raise ValueError("imagem compartilhada entre treino e validação")
    return {"valid": True, "records": len(references), "images": len({entry["sha256"] for entry in references}), "output_dir": root}

