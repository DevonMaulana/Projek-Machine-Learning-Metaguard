"""Registry-driven, deterministic v3 policy-corpus build utilities.

This module prepares a separate Chroma collection only.  It deliberately does
not change the active v0.2 retrieval path or perform a build on import.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Iterable, Mapping, Sequence

from core.policy_registry import (
    REPOSITORY_ROOT,
    PolicyRecord,
    PolicyRegistry,
    load_policy_registry,
    resolve_policy_file,
)
from rag.chunker import chunk_documents, is_meaningful_chunk
from rag.document_loader import DocumentLoadError, load_document
from rag.vector_store import DEFAULT_VECTOR_DB, MODEL_NAME, get_embedding_model


V3_COLLECTION_NAME = "metaguard_policies_v3"
MANIFEST_FILE_NAME = "metaguard_policies_v3_manifest.json"
MANIFEST_SCHEMA_VERSION = "1.0"
COLLECTION_SCHEMA_VERSION = "1.0"
CHUNKING_VERSION = "paragraph-v1"
DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 120
DEFAULT_MINIMUM_LENGTH = 150
REQUIRED_CHROMA_METADATA = (
    "policy_id",
    "source",
    "page",
    "domain_id",
    "policy_pack",
    "document_type",
    "classification",
    "effective_status",
)
EXPECTED_INITIAL_POLICY_IDS = frozenset(
    {
        "GOV-SDI-PERPRES-39-2019",
        "BPS-STANDARD-DATA-4-2020",
        "BPS-METADATA-5-2020",
        "HEALTH-SATU-DATA-18-2022",
        "EDU-SATU-DATA-31-2022",
        "ENV-SATU-DATA-25-2021",
    }
)

EmbeddingEncoder = Callable[[Sequence[str]], list[list[float]]]


class PolicyCorpusV3Error(ValueError):
    """Raised for a deterministic v3 corpus validation or build failure."""


@dataclass(frozen=True)
class ChunkingConfig:
    """Stable chunking inputs that affect identity and corpus state."""

    version: str = CHUNKING_VERSION
    chunk_size: int = DEFAULT_CHUNK_SIZE
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
    minimum_length: int = DEFAULT_MINIMUM_LENGTH

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "minimum_length": self.minimum_length,
        }


@dataclass(frozen=True)
class CorpusDocumentPlan:
    """Retrieval-relevant local source identity for one registered policy."""

    policy: PolicyRecord
    path: Path
    file_sha256: str
    file_size: int

    def retrieval_metadata(self) -> dict[str, Any]:
        """Return only scalar policy fields persisted with every chunk."""
        return {
            "policy_id": self.policy.policy_id,
            "source": self.path.name,
            "domain_id": self.policy.domain_id.value,
            "policy_pack": self.policy.policy_pack,
            "document_type": self.policy.document_type,
            "classification": self.policy.classification,
            "effective_status": self.policy.effective_status,
            "year": self.policy.year,
            "authority": self.policy.authority,
            "verification_state": self.policy.verification_state,
        }

    def fingerprint_payload(self) -> dict[str, Any]:
        """Return canonical inputs that determine persisted chunk semantics."""
        return {
            "local_file": self.policy.local_file,
            "file_sha256": self.file_sha256,
            "file_size": self.file_size,
            "metadata": self.retrieval_metadata(),
        }


@dataclass(frozen=True)
class CorpusPlan:
    """Expected retrieval-relevant v3 corpus state before embedding."""

    collection_name: str
    collection_schema_version: str
    embedding_model: str
    chunking: ChunkingConfig
    policy_registry_fingerprint: str
    registry_retrieval_fingerprint: str
    corpus_fingerprint: str
    documents: tuple[CorpusDocumentPlan, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "collection_name": self.collection_name,
            "collection_schema_version": self.collection_schema_version,
            "embedding_model": self.embedding_model,
            "chunking": self.chunking.to_dict(),
            "policy_registry_fingerprint": self.policy_registry_fingerprint,
            "registry_retrieval_fingerprint": self.registry_retrieval_fingerprint,
            "corpus_fingerprint": self.corpus_fingerprint,
            "documents": [document.fingerprint_payload() for document in self.documents],
        }


def _canonical_fingerprint(payload: Mapping[str, Any]) -> str:
    return sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_chunking(config: ChunkingConfig) -> None:
    if config.chunk_size <= 0 or config.chunk_overlap < 0 or config.chunk_overlap >= config.chunk_size:
        raise PolicyCorpusV3Error("Konfigurasi chunking tidak valid.")
    if config.minimum_length <= 0 or not config.version.strip():
        raise PolicyCorpusV3Error("Konfigurasi chunking harus memiliki version dan minimum_length valid.")


def validate_initial_policy_registry(registry: PolicyRegistry) -> None:
    """Confirm the production registry supplies exactly the approved six policies."""
    actual = {policy.policy_id for policy in registry.policies}
    if actual != EXPECTED_INITIAL_POLICY_IDS:
        raise PolicyCorpusV3Error(
            "Registry initial corpus harus memuat tepat enam policy ID yang disetujui."
        )


def _registry_retrieval_fingerprint(documents: Iterable[CorpusDocumentPlan]) -> str:
    payload = [document.fingerprint_payload()["metadata"] for document in documents]
    return _canonical_fingerprint({"documents": sorted(payload, key=lambda item: item["policy_id"])})


def compute_expected_corpus_state(
    *,
    registry: PolicyRegistry | None = None,
    repository_root: str | Path = REPOSITORY_ROOT,
    embedding_model: str = MODEL_NAME,
    chunking: ChunkingConfig = ChunkingConfig(),
    require_initial_six: bool = True,
) -> CorpusPlan:
    """Compute source/registry state without parsing PDFs or embedding text."""
    _validate_chunking(chunking)
    active_registry = registry or load_policy_registry()
    if require_initial_six:
        validate_initial_policy_registry(active_registry)
    documents = []
    for policy in sorted(active_registry.policies, key=lambda item: item.policy_id):
        try:
            path = resolve_policy_file(policy, repository_root=repository_root, require_exists=True)
        except ValueError as error:
            raise PolicyCorpusV3Error(str(error)) from error
        documents.append(
            CorpusDocumentPlan(
                policy=policy,
                path=path,
                file_sha256=_file_sha256(path),
                file_size=path.stat().st_size,
            )
        )
    documents_tuple = tuple(documents)
    retrieval_fingerprint = _registry_retrieval_fingerprint(documents_tuple)
    corpus_payload = {
        "collection_name": V3_COLLECTION_NAME,
        "collection_schema_version": COLLECTION_SCHEMA_VERSION,
        "embedding_model": embedding_model,
        "chunking": chunking.to_dict(),
        "registry_retrieval_fingerprint": retrieval_fingerprint,
        "documents": [document.fingerprint_payload() for document in documents_tuple],
    }
    return CorpusPlan(
        collection_name=V3_COLLECTION_NAME,
        collection_schema_version=COLLECTION_SCHEMA_VERSION,
        embedding_model=embedding_model,
        chunking=chunking,
        policy_registry_fingerprint=active_registry.fingerprint(),
        registry_retrieval_fingerprint=retrieval_fingerprint,
        corpus_fingerprint=_canonical_fingerprint(corpus_payload),
        documents=documents_tuple,
    )


def _stable_chunk_id(
    *,
    policy_id: str,
    page: int,
    ordinal: int,
    text: str,
    chunking: ChunkingConfig,
) -> str:
    text_digest = _canonical_fingerprint(
        {"text": text, "chunking": chunking.to_dict()}
    )[:12]
    return f"{policy_id}-p{page}-c{ordinal}-{text_digest}"


def build_stable_chunk_id(
    *,
    policy_id: str,
    page: int,
    ordinal: int,
    text: str,
    chunking: ChunkingConfig = ChunkingConfig(),
) -> str:
    """Expose deterministic v3 chunk identity for focused contract tests."""
    _validate_chunking(chunking)
    if not policy_id.strip() or page < 1 or ordinal < 1:
        raise PolicyCorpusV3Error("policy_id, page, dan ordinal chunk harus valid.")
    return _stable_chunk_id(
        policy_id=policy_id,
        page=page,
        ordinal=ordinal,
        text=text,
        chunking=chunking,
    )


def _page_count(path: Path) -> int:
    if path.suffix.casefold() == ".txt":
        return 1
    from pypdf import PdfReader

    try:
        return len(PdfReader(str(path)).pages)
    except Exception as error:
        raise PolicyCorpusV3Error(f"PDF tidak dapat dibaca: {path.name}") from error


def _build_document_chunks(
    document: CorpusDocumentPlan,
    chunking: ChunkingConfig,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        pages = load_document(document.path)
    except (DocumentLoadError, OSError, ValueError) as error:
        raise PolicyCorpusV3Error(
            f"Gagal mengekstrak policy terdaftar {document.policy.policy_id}: {error}"
        ) from error
    raw_chunks = chunk_documents(
        pages,
        chunk_size=chunking.chunk_size,
        chunk_overlap=chunking.chunk_overlap,
        minimum_length=chunking.minimum_length,
    )
    page_ordinals: dict[int, int] = {}
    chunks = []
    for raw_chunk in raw_chunks:
        text = str(raw_chunk["text"])
        if not is_meaningful_chunk(text, minimum_length=chunking.minimum_length):
            continue
        page = int(raw_chunk["page"])
        ordinal = page_ordinals.get(page, 0) + 1
        page_ordinals[page] = ordinal
        metadata = document.retrieval_metadata() | {"page": page}
        chunks.append(
            {
                "chunk_id": build_stable_chunk_id(
                    policy_id=document.policy.policy_id,
                    page=page,
                    ordinal=ordinal,
                    text=text,
                    chunking=chunking,
                ),
                "text": text,
                "metadata": metadata,
            }
        )
    if not chunks:
        raise PolicyCorpusV3Error(
            f"Policy terdaftar tidak menghasilkan chunk bermakna: {document.policy.policy_id}"
        )
    record = {
        "policy_id": document.policy.policy_id,
        "local_file": document.policy.local_file,
        "file_sha256": document.file_sha256,
        "file_size": document.file_size,
        "page_count": _page_count(document.path),
        "text_extractable_page_count": len(pages),
        "chunk_count": len(chunks),
        "registry_retrieval_fingerprint": _canonical_fingerprint(document.fingerprint_payload()["metadata"]),
    }
    return chunks, record


def manifest_path(vector_db_path: str | Path = DEFAULT_VECTOR_DB) -> Path:
    """Return the generated, ignored manifest location next to the local store."""
    return Path(vector_db_path) / MANIFEST_FILE_NAME


def read_corpus_manifest(vector_db_path: str | Path = DEFAULT_VECTOR_DB) -> dict[str, Any] | None:
    """Read a completed manifest, returning ``None`` only when it is absent."""
    path = manifest_path(vector_db_path)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise PolicyCorpusV3Error(f"Manifest corpus v3 tidak valid: {path}") from error
    if not isinstance(raw, dict):
        raise PolicyCorpusV3Error("Manifest corpus v3 harus berupa object JSON.")
    return raw


def _write_manifest_atomic(path: Path, manifest: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as stream:
        stream.write(serialized)
        temporary_path = Path(stream.name)
    try:
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _create_client(vector_db_path: str | Path) -> Any:
    import chromadb
    from chromadb.config import Settings

    return chromadb.PersistentClient(
        path=str(vector_db_path),
        settings=Settings(anonymized_telemetry=False),
    )


def _get_existing_collection(client: Any) -> Any | None:
    try:
        return client.get_collection(V3_COLLECTION_NAME)
    except Exception:  # Chroma emits version-specific missing-collection errors.
        return None


def _is_scalar_metadata(metadata: Mapping[str, Any]) -> bool:
    return all(type(value) in {str, int, float, bool} for value in metadata.values())


def verify_persisted_corpus(
    *,
    plan: CorpusPlan,
    vector_db_path: str | Path = DEFAULT_VECTOR_DB,
    manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify persisted v3 chunks and manifest identity without retrieval ranking."""
    active_manifest = dict(manifest) if manifest is not None else read_corpus_manifest(vector_db_path)
    if active_manifest is None:
        raise PolicyCorpusV3Error("Manifest corpus v3 belum tersedia.")
    if active_manifest.get("corpus_fingerprint") != plan.corpus_fingerprint:
        raise PolicyCorpusV3Error("Fingerprint manifest tidak sesuai expected corpus state.")
    client = _create_client(vector_db_path)
    collection = _get_existing_collection(client)
    if collection is None:
        raise PolicyCorpusV3Error("Collection v3 tidak tersedia.")
    stored = collection.get(include=["documents", "metadatas"])
    ids = list(stored.get("ids", []))
    metadatas = list(stored.get("metadatas", []))
    documents = list(stored.get("documents", []))
    expected_count = int(active_manifest.get("total_chunks", -1))
    if len(ids) != expected_count or int(collection.count()) != expected_count:
        raise PolicyCorpusV3Error("Jumlah chunk persisted tidak sesuai manifest.")
    if len(ids) != len(set(ids)) or len(metadatas) != len(ids) or len(documents) != len(ids):
        raise PolicyCorpusV3Error("ID atau payload chunk persisted tidak konsisten.")
    expected_by_id = {document.policy.policy_id: document for document in plan.documents}
    seen_policy_ids = set()
    for metadata in metadatas:
        if not isinstance(metadata, Mapping):
            raise PolicyCorpusV3Error("Metadata chunk persisted tidak valid.")
        if any(field not in metadata for field in REQUIRED_CHROMA_METADATA):
            raise PolicyCorpusV3Error("Metadata chunk tidak memiliki field routing wajib.")
        if not _is_scalar_metadata(metadata):
            raise PolicyCorpusV3Error("Metadata chunk harus scalar kompatibel dengan Chroma.")
        policy_id = metadata["policy_id"]
        expected = expected_by_id.get(policy_id)
        if expected is None:
            raise PolicyCorpusV3Error("Chunk memuat policy_id di luar registry corpus.")
        required = expected.retrieval_metadata()
        if any(metadata.get(key) != value for key, value in required.items()):
            raise PolicyCorpusV3Error("Metadata chunk tidak sesuai policy registry.")
        seen_policy_ids.add(policy_id)
    if seen_policy_ids != set(expected_by_id):
        raise PolicyCorpusV3Error("Tidak semua policy registry terwakili pada collection.")
    return {
        "collection_name": V3_COLLECTION_NAME,
        "chunk_count": len(ids),
        "policy_ids": sorted(seen_policy_ids),
        "persistent_reopen_verified": True,
    }


def needs_corpus_rebuild(
    *,
    vector_db_path: str | Path = DEFAULT_VECTOR_DB,
    registry: PolicyRegistry | None = None,
    repository_root: str | Path = REPOSITORY_ROOT,
    embedding_model: str = MODEL_NAME,
    chunking: ChunkingConfig = ChunkingConfig(),
    require_initial_six: bool = True,
) -> bool:
    """Return whether v3 manifest, inputs, or persisted collection are stale."""
    plan = compute_expected_corpus_state(
        registry=registry,
        repository_root=repository_root,
        embedding_model=embedding_model,
        chunking=chunking,
        require_initial_six=require_initial_six,
    )
    manifest = read_corpus_manifest(vector_db_path)
    if manifest is None or manifest.get("corpus_fingerprint") != plan.corpus_fingerprint:
        return True
    try:
        verify_persisted_corpus(plan=plan, vector_db_path=vector_db_path, manifest=manifest)
    except PolicyCorpusV3Error:
        return True
    return False


def _default_encoder(texts: Sequence[str]) -> list[list[float]]:
    model = get_embedding_model()
    return model.encode(list(texts), normalize_embeddings=True).tolist()


def rebuild_policy_corpus_v3(
    *,
    vector_db_path: str | Path = DEFAULT_VECTOR_DB,
    registry: PolicyRegistry | None = None,
    repository_root: str | Path = REPOSITORY_ROOT,
    embedding_model: str = MODEL_NAME,
    chunking: ChunkingConfig = ChunkingConfig(),
    encoder: EmbeddingEncoder | None = None,
    require_initial_six: bool = True,
) -> dict[str, Any]:
    """Fully rebuild only the v3 collection and atomically write its manifest."""
    plan = compute_expected_corpus_state(
        registry=registry,
        repository_root=repository_root,
        embedding_model=embedding_model,
        chunking=chunking,
        require_initial_six=require_initial_six,
    )
    all_chunks: list[dict[str, Any]] = []
    document_records = []
    for document in plan.documents:
        chunks, record = _build_document_chunks(document, plan.chunking)
        all_chunks.extend(chunks)
        document_records.append(record)
    chunk_ids = [chunk["chunk_id"] for chunk in all_chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise PolicyCorpusV3Error("Chunk ID v3 duplikat; rebuild dihentikan.")
    if not all(_is_scalar_metadata(chunk["metadata"]) for chunk in all_chunks):
        raise PolicyCorpusV3Error("Metadata chunk v3 harus scalar.")

    target_manifest = manifest_path(vector_db_path)
    target_manifest.unlink(missing_ok=True)
    client = _create_client(vector_db_path)
    try:
        client.delete_collection(V3_COLLECTION_NAME)
    except Exception:
        pass
    collection = client.get_or_create_collection(V3_COLLECTION_NAME)
    active_encoder = encoder or _default_encoder
    try:
        texts = [chunk["text"] for chunk in all_chunks]
        embeddings = active_encoder(texts)
        if len(embeddings) != len(all_chunks):
            raise PolicyCorpusV3Error("Encoder tidak mengembalikan embedding untuk setiap chunk.")
        collection.add(
            ids=chunk_ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=[chunk["metadata"] for chunk in all_chunks],
        )
        manifest = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "collection_name": V3_COLLECTION_NAME,
            "collection_schema_version": COLLECTION_SCHEMA_VERSION,
            "embedding_model": embedding_model,
            "chunking": chunking.to_dict(),
            "policy_registry_fingerprint": plan.policy_registry_fingerprint,
            "registry_retrieval_fingerprint": plan.registry_retrieval_fingerprint,
            "corpus_fingerprint": plan.corpus_fingerprint,
            "document_records": document_records,
            "total_documents": len(document_records),
            "total_chunks": len(all_chunks),
        }
        verification = verify_persisted_corpus(
            plan=plan,
            vector_db_path=vector_db_path,
            manifest=manifest,
        )
    except Exception:
        target_manifest.unlink(missing_ok=True)
        raise
    _write_manifest_atomic(target_manifest, manifest)
    return {**manifest, "verification": verification, "manifest_path": str(target_manifest)}
