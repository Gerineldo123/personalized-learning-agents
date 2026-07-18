import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.course_kb_service import (  # noqa: E402
    load_course_documents,
    validate_course_corpus,
)
from services.rag_service import RAGService  # noqa: E402
from agents.base import AgentState  # noqa: E402
from agents.chat_agent import ChatAgent  # noqa: E402


class FakeCollection:
    def __init__(self, records=None):
        self.records = dict(records or {})

    def count(self):
        return len(self.records)

    def get(self, where=None, include=None):
        values = [
            (item_id, record)
            for item_id, record in self.records.items()
            if not where or all(record.get("metadata", {}).get(key) == value for key, value in where.items())
        ]
        return {
            "ids": [item_id for item_id, _record in values],
            "documents": [record.get("document", "") for _item_id, record in values],
            "metadatas": [record.get("metadata", {}) for _item_id, record in values],
        }

    def delete(self, ids=None, where=None):
        if ids:
            for item_id in ids:
                self.records.pop(item_id, None)
        if where:
            for item_id, record in list(self.records.items()):
                metadata = record.get("metadata", {})
                if all(metadata.get(key) == value for key, value in where.items()):
                    self.records.pop(item_id, None)

    def upsert(self, ids, documents, metadatas):
        for item_id, document, metadata in zip(ids, documents, metadatas):
            self.records[item_id] = {"document": document, "metadata": metadata, "distance": 0.1}

    def query(self, query_texts, n_results, where=None):
        values = [
            (item_id, record)
            for item_id, record in self.records.items()
            if not where or all(record.get("metadata", {}).get(key) == value for key, value in where.items())
        ][:n_results]
        return {
            "ids": [[item_id for item_id, _record in values]],
            "documents": [[record.get("document", "") for _item_id, record in values]],
            "distances": [[record.get("distance", 0.1) for _item_id, record in values]],
            "metadatas": [[record.get("metadata", {}) for _item_id, record in values]],
        }


class CourseKnowledgeBaseTests(unittest.TestCase):
    def make_service(self, course_records=None, user_records=None):
        service = RAGService.__new__(RAGService)
        service.course_collection = FakeCollection(course_records)
        service.collection = FakeCollection(user_records)
        return service

    def test_course_corpus_is_complete_and_uses_exact_graph_nodes(self):
        status = validate_course_corpus()
        self.assertTrue(status["ready"])
        self.assertEqual(status["course_name"], "数据结构")
        self.assertGreaterEqual(status["document_count"], 10)
        self.assertGreaterEqual(status["rendered_character_count"], 50000)
        self.assertEqual(
            set(status["knowledge_points"]),
            {"线性表", "栈与队列", "树与二叉树", "图", "查找算法", "排序算法", "哈希表"},
        )

    def test_every_source_document_contains_code_and_answer(self):
        documents = load_course_documents(expand_practice=False)
        self.assertGreaterEqual(len(documents), 10)
        for document in documents:
            content = document["content"]
            self.assertIn("```", content, document["title"])
            self.assertIn("答案", content, document["title"])

    def test_seed_is_idempotent(self):
        service = self.make_service()
        first = service.seed_course_knowledge_base()
        first_ids = set(service.course_collection.records)
        second = service.seed_course_knowledge_base()
        self.assertEqual(first["document_count"], second["document_count"])
        self.assertEqual(first["chunk_count"], second["chunk_count"])
        self.assertEqual(first_ids, set(service.course_collection.records))

    def test_ensure_skips_reindex_when_hashes_match(self):
        records = {}
        for document in load_course_documents(expand_practice=True):
            records[f"kb:{document['id']}:0"] = {
                "document": document["content"],
                "metadata": {
                    "document_id": document["id"],
                    "content_hash": document["content_hash"],
                    "course_name": "数据结构",
                    "indexed_at": "2026-01-01T00:00:00+00:00",
                },
            }
        service = self.make_service(course_records=records)
        service.seed_course_knowledge_base = Mock(side_effect=AssertionError("不应重复索引"))
        status = service.ensure_course_knowledge_base()
        self.assertTrue(status["ready"])
        service.seed_course_knowledge_base.assert_not_called()

    def test_search_merges_system_and_current_user_only(self):
        course_records = {
            "kb:sort:0": {
                "document": "快速排序最坏情况出现在划分极不均衡时。",
                "distance": 0.1,
                "metadata": {
                    "scope": "system",
                    "document_id": "ds-06-sort",
                    "course_name": "数据结构",
                    "title": "排序算法",
                    "chapter": "排序算法",
                    "knowledge_points": "[\"排序算法\"]",
                    "source": "team_constructed",
                },
            },
        }
        user_records = {
            "res_12_chunk_0": {
                "document": "用户自己的快速排序复习笔记。",
                "distance": 0.2,
                "metadata": {"scope": "user", "user_id": "u1", "resource_db_id": 12},
            },
            "res_99_chunk_0": {
                "document": "其他用户的私有笔记。",
                "distance": 0.05,
                "metadata": {"scope": "user", "user_id": "u2", "resource_db_id": 99},
            },
        }
        service = self.make_service(course_records, user_records)
        result = service.search("快速排序最坏情况", "u1", top_k=5)
        self.assertEqual(result["ids"], ["system:ds-06-sort", "12"])
        self.assertEqual([item["scope"] for item in result["sources"]], ["system", "user"])
        self.assertNotIn("其他用户", "".join(result["documents"]))

    def test_specific_course_chapter_ranks_before_overview(self):
        records = {
            "kb:overview:0": {
                "document": "课程导论也会提到二叉树遍历。",
                "distance": 0.05,
                "metadata": {
                    "scope": "system",
                    "document_id": "overview",
                    "title": "数据结构课程导论",
                    "chapter": "课程导论",
                    "knowledge_points": "[\"线性表\", \"栈与队列\", \"树与二叉树\", \"图\"]",
                },
            },
            "kb:tree:0": {
                "document": "二叉树遍历包括前序、中序、后序和层序遍历。",
                "distance": 0.2,
                "metadata": {
                    "scope": "system",
                    "document_id": "tree",
                    "title": "树与二叉树：层次结构、遍历与编码",
                    "chapter": "树与二叉树",
                    "knowledge_points": "[\"树与二叉树\"]",
                },
            },
        }
        service = self.make_service(course_records=records)
        result = service.search("二叉树遍历", "new-user", top_k=2)
        self.assertEqual(result["ids"][0], "system:tree")

    def test_chat_rag_query_removes_source_instruction(self):
        message = "快速排序的最坏时间复杂度是什么？请根据预制课程知识库回答并标明资料来源。"
        self.assertEqual(ChatAgent._rag_query(message), "快速排序的最坏时间复杂度是什么")

    def test_chat_rag_context_declares_evidence_hit(self):
        result = {
            "documents": ["若枢轴划分极端不平衡，快速排序最坏退化为 O(n^2)。"],
            "sources": [{"course_name": "数据结构", "chapter": "排序算法"}],
        }
        state = AgentState(
            user_id="u1",
            user_message="快速排序的最坏时间复杂度是什么？请根据预制课程知识库回答并标明资料来源。",
        )
        with patch("agents.chat_agent.search_rag", return_value=result) as search:
            context = ChatAgent()._build_rag_context(state)

        search.assert_called_once_with("快速排序的最坏时间复杂度是什么", "u1", top_k=6)
        self.assertIn("资料检索状态：已命中", context)
        self.assertIn("数据结构 · 排序算法", context)
        self.assertIn("不得声称知识库未提供", context)

    def test_chat_rag_relevance_prioritizes_core_subject(self):
        agent = ChatAgent()
        query = "快速排序的最坏时间复杂度是什么"
        tree_score = agent._rag_relevance(
            query,
            "树结构分析也需要讨论时间复杂度和递归边界。",
            {"course_name": "数据结构", "chapter": "树与二叉树"},
        )
        sort_score = agent._rag_relevance(
            query,
            "快速排序在枢轴极端不平衡时，最坏时间复杂度退化为 O(n^2)。",
            {"course_name": "数据结构", "chapter": "排序算法"},
        )
        self.assertGreater(sort_score, tree_score)


if __name__ == "__main__":
    unittest.main()
