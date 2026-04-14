from __future__ import annotations

import hashlib
import re
from collections import Counter


def normalize_text(text: str) -> str:
    normalized = re.sub(r"https?://\S+", " ", text.lower())
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def shingles(text: str, size: int = 3) -> set[str]:
    tokens = normalize_text(text).split()
    if len(tokens) < size:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[i : i + size]) for i in range(len(tokens) - size + 1)}


def jaccard_similarity(left: str, right: str) -> float:
    left_shingles = shingles(left)
    right_shingles = shingles(right)
    if not left_shingles or not right_shingles:
        return 0.0
    return len(left_shingles & right_shingles) / len(left_shingles | right_shingles)


def simhash(text: str) -> str:
    features = Counter(normalize_text(text).split())
    vector = [0] * 64
    for token, weight in features.items():
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bits = int.from_bytes(digest, byteorder="big")
        for index in range(64):
            vector[index] += weight if bits & (1 << index) else -weight
    value = 0
    for index, score in enumerate(vector):
        if score > 0:
            value |= 1 << index
    return f"{value:016x}"


def hamming_distance(left: str, right: str) -> int:
    return bin(int(left, 16) ^ int(right, 16)).count("1")


def fingerprint_job(company: str, title: str, description: str) -> str:
    basis = f"{company}|{title}|{normalize_text(description)[:2048]}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def are_near_duplicates(left: str, right: str) -> bool:
    jaccard = jaccard_similarity(left, right)
    if jaccard >= 0.75:
        return True
    return hamming_distance(simhash(left), simhash(right)) <= 8
