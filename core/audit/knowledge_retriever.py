# -*- coding: utf-8 -*-
"""core/audit/knowledge_retriever.py —— 知识检索与复用引擎。

基于第一性原理：
    沉淀知识的目的是为了复用。
    不能检索的知识库 = 死知识。
    遇到问题时自动匹配历史经验 = 站在过去的肩膀上。

核心功能：
1. 相似故障检索：遇到问题时，快速找到历史解决方案
2. 相似案例检索：交易前，看看历史上类似情况怎么做的
3. 经验推荐：决策时自动引用相关历史教训
"""
from __future__ import annotations

import logging
from typing import Optional, List, Dict

from .db_writer import _get_pg_conn

logger = logging.getLogger("core.audit.retriever")


# ------------------------------------------------------------------
# 知识检索器
# ------------------------------------------------------------------
class KnowledgeRetriever:
    """知识检索引擎。

    用法：
        retriever = KnowledgeRetriever()

        # 遇到问题时检索相似故障
        solutions = retriever.search_faults("下单失败 连接超时")

        # 交易前检索相似案例
        cases = retriever.search_cases("XAUUSD 突破 2000")
    """

    def search_faults(self,
                      keyword: str,
                      limit: int = 5,
                      category: Optional[str] = None) -> List[Dict]:
        """检索相似故障知识库。

        Args:
            keyword: 搜索关键词（症状/错误信息）
            limit: 返回条数
            category: 限定分类

        Returns:
            匹配的故障知识列表
        """
        conn = _get_pg_conn()
        if conn is None:
            return []

        try:
            sql = """
                SELECT fault_uid, title, symptom, root_cause, solution,
                       category, severity, occurrence_count, confidence_score
                FROM qd_fault_knowledge
                WHERE verified = true
                  AND (
                    title ILIKE %s OR
                    symptom ILIKE %s OR
                    root_cause ILIKE %s
                  )
            """
            params = [f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"]

            if category:
                sql += " AND category = %s"
                params.append(category)

            sql += " ORDER BY confidence_score DESC, occurrence_count DESC LIMIT %s"
            params.append(limit)

            with conn.cursor() as cur:
                cur.execute(sql, params)
                columns = [desc[0] for desc in cur.description]
                results = [dict(zip(columns, row)) for row in cur.fetchall()]

            if results:
                logger.info("found %d similar faults for: %s", len(results), keyword)

            return results

        except Exception as e:
            logger.warning("fault search failed: %s", e)
            return []

    def search_post_mortems(self,
                            keyword: str,
                            limit: int = 5) -> List[Dict]:
        """检索相似复盘案例。

        Args:
            keyword: 搜索关键词
            limit: 返回条数

        Returns:
            匹配的复盘记录列表
        """
        conn = _get_pg_conn()
        if conn is None:
            return []

        try:
            sql = """
                SELECT post_mortem_uid, title, post_mortem_type, severity,
                       what_happened, why_it_happened, what_we_learned,
                       how_to_improve, root_cause_category, status
                FROM qd_post_mortems
                WHERE status = 'closed'
                  AND (
                    title ILIKE %s OR
                    what_happened ILIKE %s OR
                    what_we_learned ILIKE %s
                  )
                ORDER BY created_at DESC LIMIT %s
            """
            params = [f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", limit]

            with conn.cursor() as cur:
                cur.execute(sql, params)
                columns = [desc[0] for desc in cur.description]
                results = [dict(zip(columns, row)) for row in cur.fetchall()]

            return results

        except Exception as e:
            logger.warning("post-mortem search failed: %s", e)
            return []

    def get_lessons_for_decision(self,
                                 symbol: str,
                                 side: str,
                                 signal_type: str) -> List[str]:
        """决策前获取相关历史教训。

        在每次交易决策前调用，自动检索相关的历史经验。

        Args:
            symbol: 交易品种
            side: 方向（buy/sell）
            signal_type: 信号类型（breakout/trend/range等）

        Returns:
            相关的教训列表（字符串）
        """
        lessons = []

        # 1. 检索相关故障
        faults = self.search_faults(f"{symbol} {side}")
        for f in faults[:3]:
            lessons.append(f"⚠️ 历史故障参考: {f['title']} → {f['solution']}")

        # 2. 检索相关复盘
        post_mortems = self.search_post_mortems(f"{symbol} {side}")
        for pm in post_mortems[:2]:
            lessons.append(f"📚 历史教训: {pm['what_we_learned'][:100]}")

        if lessons:
            logger.info("found %d lessons for %s %s", len(lessons), symbol, side)

        return lessons

    def get_knowledge_stats(self) -> Dict:
        """获取知识库统计信息。"""
        conn = _get_pg_conn()
        if conn is None:
            return {}

        try:
            with conn.cursor() as cur:
                # 故障知识统计
                cur.execute("SELECT COUNT(*) FROM qd_fault_knowledge")
                fault_count = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM qd_fault_knowledge WHERE verified = true")
                verified_faults = cur.fetchone()[0]

                # 复盘统计
                cur.execute("SELECT COUNT(*) FROM qd_post_mortems")
                pm_count = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM qd_post_mortems WHERE status = 'closed'")
                closed_pm = cur.fetchone()[0]

                # 实验统计
                cur.execute("SELECT COUNT(*) FROM qd_experiment_logs")
                exp_count = cur.fetchone()[0]

            return {
                "fault_knowledge": {
                    "total": fault_count,
                    "verified": verified_faults,
                },
                "post_mortems": {
                    "total": pm_count,
                    "closed": closed_pm,
                },
                "experiments": {
                    "total": exp_count,
                },
            }

        except Exception as e:
            logger.warning("stats query failed: %s", e)
            return {}


# ------------------------------------------------------------------
# 单例模式
# ------------------------------------------------------------------
_retriever_instance: Optional[KnowledgeRetriever] = None


def get_knowledge_retriever() -> KnowledgeRetriever:
    """获取全局知识检索器单例。"""
    global _retriever_instance
    if _retriever_instance is None:
        _retriever_instance = KnowledgeRetriever()
    return _retriever_instance
