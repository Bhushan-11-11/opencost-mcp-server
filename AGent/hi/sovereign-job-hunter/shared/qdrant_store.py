from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from shared.schemas import ResumeClaim


@dataclass
class QdrantConfig:
    storage_path: str
    collection_name: str
    vector_size: int


class QdrantClaimStore:
    def __init__(self, config: QdrantConfig) -> None:
        self.config = config
        path = Path(config.storage_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.client = QdrantClient(path=str(path))
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        exists = self.client.collection_exists(self.config.collection_name)
        if exists:
            return
        self.client.create_collection(
            collection_name=self.config.collection_name,
            vectors_config=qmodels.VectorParams(
                size=self.config.vector_size,
                distance=qmodels.Distance.COSINE,
            ),
        )

    def upsert_claims(self, claims: list[ResumeClaim], vectors: list[list[float]]) -> None:
        points = []
        for idx, (claim, vector) in enumerate(zip(claims, vectors, strict=False), start=1):
            payload = {
                "claim_id": claim.claim_id,
                "text": claim.text,
                "skill_tags": claim.skill_tags,
            }
            points.append(
                qmodels.PointStruct(
                    id=idx,
                    vector=vector,
                    payload=payload,
                )
            )
        if points:
            self.client.upsert(collection_name=self.config.collection_name, points=points, wait=True)

    def search_claim_ids(self, query_vector: list[float], top_k: int = 12) -> list[str]:
        results = self.client.query_points(
            collection_name=self.config.collection_name,
            query=query_vector,
            limit=top_k,
            with_payload=True,
        )
        claim_ids: list[str] = []
        for point in results.points:
            payload = point.payload or {}
            claim_id = payload.get("claim_id")
            if isinstance(claim_id, str):
                claim_ids.append(claim_id)
        return claim_ids
