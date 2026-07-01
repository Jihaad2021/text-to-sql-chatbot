"""
BaselineCache — pre-computed statistical baselines for all partners and channels.

Loaded once at startup from the last 90 days of data. Provides mean, std dev,
and z-score helpers so the rest of the system can say "X is above/below normal"
without recomputing statistics on every query.
"""

import math
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine


class BaselineCache:
    """
    Holds pre-computed per-partner and per-channel baselines.

    Attributes:
        partner  — dict keyed by partner name → {trx_mean, trx_std, rev_mean, rev_std, sr_mean}
        channel  — dict keyed by channel name → same structure
        overall  — aggregate daily stats → {trx_mean, trx_std, rev_mean, rev_std}
        period   — {'start': date, 'end': date, 'days': int}
    """

    def __init__(self, engine: Engine) -> None:
        self.partner: dict[str, dict] = {}
        self.channel: dict[str, dict] = {}
        self.overall: dict[str, float] = {}
        self.period: dict[str, Any] = {}
        self._load(engine)

    # ── public helpers ────────────────────────────────────────────

    def z_score(self, value: float, mean: float, std: float) -> float | None:
        """Return z-score, or None if std is zero."""
        if std == 0:
            return None
        return round((value - mean) / std, 2)

    def classify_change(self, pct_change: float) -> str:
        """Classify a percentage change as normal / significant / extreme."""
        abs_pct = abs(pct_change)
        if abs_pct < 15:
            return "normal"
        if abs_pct < 35:
            return "significant"
        return "extreme"

    def partner_context(self, partner: str) -> dict | None:
        """Return baseline dict for a partner, or None if not found."""
        return self.partner.get(partner)

    def channel_context(self, channel: str) -> dict | None:
        return self.channel.get(channel)

    def narrative(self) -> str:
        """
        Return a compact narrative string (~600 chars) summarising baselines.
        Injected into LLM prompts as business context.
        """
        lines = [
            f"=== BASELINE HARIAN (rata-rata {self.period.get('days', 0)} hari, "
            f"{self.period.get('start')} → {self.period.get('end')}) ===",
            f"Total harian: rata-rata {self._fmt_trx(self.overall.get('trx_mean', 0))} transaksi, "
            f"revenue Rp {self._fmt_rev(self.overall.get('rev_mean', 0))}",
            "",
            "Top partner (rata-rata harian):",
        ]

        # Top 5 by trx_mean
        top = sorted(self.partner.items(), key=lambda x: x[1].get("trx_mean", 0), reverse=True)[:5]
        for name, b in top:
            sr = b.get("sr_mean", 0)
            lines.append(
                f"  {name}: {self._fmt_trx(b['trx_mean'])} trx/hari "
                f"(±{self._fmt_trx(b['trx_std'])}), SR {sr:.1f}%"
            )

        lines += ["", "Channel (rata-rata harian):"]
        for name, b in sorted(self.channel.items(), key=lambda x: x[1].get("trx_mean", 0), reverse=True):
            lines.append(
                f"  {name}: {self._fmt_trx(b['trx_mean'])} trx/hari "
                f"(±{self._fmt_trx(b['trx_std'])})"
            )

        return "\n".join(lines)

    # ── private ───────────────────────────────────────────────────

    def _load(self, engine: Engine) -> None:
        """Compute baselines from last 90 days of data."""
        with engine.connect() as conn:
            self._load_period(conn)
            self._load_overall(conn)
            self._load_partners(conn)
            self._load_channels(conn)

    def _load_period(self, conn) -> None:
        row = conn.execute(text("""
            SELECT MIN(date)::date, MAX(date)::date,
                   COUNT(DISTINCT date::date)
            FROM daily_master
            WHERE date >= CURRENT_DATE - INTERVAL '90 days'
        """)).fetchone()
        self.period = {"start": str(row[0]), "end": str(row[1]), "days": row[2]}

    def _load_overall(self, conn) -> None:
        row = conn.execute(text("""
            SELECT
                AVG(daily_trx)         AS trx_mean,
                STDDEV(daily_trx)      AS trx_std,
                AVG(daily_rev)         AS rev_mean,
                STDDEV(daily_rev)      AS rev_std
            FROM (
                SELECT date::date,
                       SUM(total_trx)     AS daily_trx,
                       SUM(total_revenue) AS daily_rev
                FROM daily_master
                WHERE date >= CURRENT_DATE - INTERVAL '90 days'
                GROUP BY date::date
            ) d
        """)).fetchone()
        self.overall = {
            "trx_mean": float(row[0] or 0),
            "trx_std":  float(row[1] or 0),
            "rev_mean": float(row[2] or 0),
            "rev_std":  float(row[3] or 0),
        }

    def _load_partners(self, conn) -> None:
        rows = conn.execute(text("""
            SELECT
                partner,
                AVG(daily_trx)    AS trx_mean,
                STDDEV(daily_trx) AS trx_std,
                AVG(daily_rev)    AS rev_mean,
                STDDEV(daily_rev) AS rev_std,
                AVG(daily_sr)     AS sr_mean
            FROM (
                SELECT date::date, partner,
                       SUM(total_trx)     AS daily_trx,
                       SUM(total_revenue) AS daily_rev,
                       ROUND((SUM(success_trx)::numeric /
                              NULLIF(SUM(total_trx), 0)) * 100, 2) AS daily_sr
                FROM daily_master
                WHERE date >= CURRENT_DATE - INTERVAL '90 days'
                GROUP BY date::date, partner
            ) d
            GROUP BY partner
        """)).fetchall()
        for row in rows:
            self.partner[row[0]] = {
                "trx_mean": float(row[1] or 0),
                "trx_std":  float(row[2] or 0),
                "rev_mean": float(row[3] or 0),
                "rev_std":  float(row[4] or 0),
                "sr_mean":  float(row[5] or 0),
            }

    def _load_channels(self, conn) -> None:
        rows = conn.execute(text("""
            SELECT
                channel,
                AVG(daily_trx)    AS trx_mean,
                STDDEV(daily_trx) AS trx_std,
                AVG(daily_rev)    AS rev_mean,
                STDDEV(daily_rev) AS rev_std
            FROM (
                SELECT date::date, channel,
                       SUM(total_trx)     AS daily_trx,
                       SUM(total_revenue) AS daily_rev
                FROM channel_payment
                WHERE date >= CURRENT_DATE - INTERVAL '90 days'
                GROUP BY date::date, channel
            ) d
            GROUP BY channel
        """)).fetchall()
        for row in rows:
            self.channel[row[0]] = {
                "trx_mean": float(row[1] or 0),
                "trx_std":  float(row[2] or 0),
                "rev_mean": float(row[3] or 0),
                "rev_std":  float(row[4] or 0),
            }

    @staticmethod
    def _fmt_trx(n: float) -> str:
        if n >= 1_000_000:
            return f"{n/1_000_000:.1f}jt"
        if n >= 1_000:
            return f"{n/1_000:.1f}rb"
        return str(int(n))

    @staticmethod
    def _fmt_rev(n: float) -> str:
        if n >= 1_000_000_000:
            return f"{n/1_000_000_000:.1f} miliar"
        if n >= 1_000_000:
            return f"{n/1_000_000:.1f} juta"
        return f"{int(n):,}"
