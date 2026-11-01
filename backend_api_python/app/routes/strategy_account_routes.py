"""Account snapshot and account position routes used by strategy screens."""
import traceback

from flask import g, jsonify, request

from app.routes.strategy_blueprint import strategy_blp
from app.utils.auth import login_required
from app.utils.logger import get_logger


logger = get_logger(__name__)


def _first_okx_credential_id(user_id: int):
    """Pick the user's first OKX credential id that decrypts cleanly."""
    try:
        from app.utils.db import get_db_connection

        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                "SELECT id FROM qd_exchange_credentials "
                "WHERE user_id=%s AND exchange_id='okx' ORDER BY id LIMIT 5",
                (int(user_id),),
            )
            ids = [r['id'] for r in cur.fetchall() or []]
            cur.close()
        for cid in ids:
            from app.services.exchange_execution import resolve_exchange_config

            cfg = resolve_exchange_config({'credential_id': cid}, user_id=int(user_id))
            if cfg.get('api_key'):
                return cid
        return None
    except Exception as e:
        logger.warning(f"_first_okx_credential_id failed: {e}")
        return None


@strategy_blp.route('/account/snapshot', methods=['GET'])
@login_required
def get_account_snapshot():
    """Live swap/spot positions + open orders for a saved credential."""
    try:
        user_id = g.user_id
        credential_id = request.args.get('credential_id', type=int)
        if not credential_id:
            return jsonify({
                'code': 0,
                'msg': 'Missing credential_id',
                'data': {'swap_positions': [], 'spot_positions': [], 'open_orders': []},
            }), 400

        from app.services.live_trading.account_snapshot import fetch_account_snapshot

        snap = fetch_account_snapshot(user_id=int(user_id), credential_id=int(credential_id))
        msg = "success"
        if snap.get("error"):
            msg = str(snap.get("error") or "")
        elif snap.get("warnings"):
            msg = str(snap["warnings"][0])
        return jsonify({'code': 1, 'msg': msg, 'data': snap})
    except Exception as e:
        logger.error(f"get_account_snapshot failed: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'code': 0,
            'msg': str(e),
            'data': {'swap_positions': [], 'spot_positions': [], 'open_orders': []},
        }), 500


@strategy_blp.route('/account/positions', methods=['GET'])
@login_required
def get_account_positions():
    """L1 account position mirror for Quick Trade / asset views."""
    try:
        user_id = g.user_id
        credential_id = request.args.get('credential_id', type=int)
        market_type = request.args.get('market_type', type=str)

        from app.services.live_trading.account_positions import list_account_positions

        rows = list_account_positions(
            user_id=int(user_id),
            credential_id=credential_id,
            market_type=market_type,
        )

        # total_equity: best-effort OKX balance via the standard credential→factory chain.
        # Never blocks the positions response when the balance lookup fails.
        total_equity = None
        try:
            cid = credential_id or _first_okx_credential_id(int(user_id))
            if cid:
                from app.services.exchange_execution import resolve_exchange_config
                from app.services.live_trading.factory import create_client

                cfg = resolve_exchange_config({'credential_id': cid}, user_id=int(user_id))
                if str(cfg.get('exchange_id') or '').lower() == 'okx':
                    client = create_client(cfg, market_type=market_type or 'swap')
                    bal = client.get_balance()
                    arr = bal.get('data') or []
                    if arr and isinstance(arr[0], dict) and arr[0].get('totalEq') is not None:
                        total_equity = f"${float(arr[0]['totalEq']):,.2f}"
        except Exception as e:
            logger.warning(f"get_account_positions total_equity lookup skipped: {e}")

        return jsonify({
            'code': 1,
            'msg': 'success',
            'data': {'positions': rows, 'items': rows, 'total_equity': total_equity},
        })
    except Exception as e:
        logger.error(f"get_account_positions failed: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'code': 0, 'msg': str(e), 'data': {'positions': [], 'items': []}}), 500
