# -*- coding: utf-8 -*-
"""dashboard_data.py —— 从数据库查询Dashboard数据。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.audit.db_writer import _get_pg_conn

def get_dashboard_data():
    conn = _get_pg_conn()
    if conn is None:
        return {}

    stats = {}

    with conn.cursor() as cur:
        # 知识统计
        for table in ['qd_ai_decisions', 'qd_post_mortems', 'qd_fault_knowledge', 'qd_experiment_logs', 'qd_trade_journal']:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            stats[table] = cur.fetchone()[0]

        # 绩效归因
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE net_pnl > 0) as wins,
                ROUND(AVG(net_pnl), 2) as avg_pnl,
                ROUND(AVG(r_multiple), 2) as avg_r,
                ROUND(SUM(net_pnl), 2) as total_pnl
            FROM qd_trade_journal WHERE status = 'closed'
        """)
        row = cur.fetchone()
        stats['performance'] = {
            'total_trades': row[0],
            'wins': row[1],
            'avg_pnl': float(row[2]) if row[2] else 0,
            'avg_r': float(row[3]) if row[3] else 0,
            'total_pnl': float(row[4]) if row[4] else 0,
        }
        stats['performance']['win_rate'] = round(row[1] / row[0] * 100, 1) if row[0] > 0 else 0

    return stats

if __name__ == "__main__":
    import json
    data = get_dashboard_data()
    print(json.dumps(data, indent=2, ensure_ascii=False))
