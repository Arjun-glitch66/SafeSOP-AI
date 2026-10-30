"""limit/offset paging for list endpoints. Responses keep their list key and add total/limit/offset."""
from dataclasses import dataclass

from fastapi import Query


@dataclass
class Page:
    limit: int
    offset: int


def page_params(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    return Page(limit, offset)


def paginate(connection, sql, params, page, key):
    """Run `sql` (which must end with its ORDER BY) for one page, plus the total row count."""
    total = connection.execute(f"SELECT COUNT(*) FROM ({sql}) AS counted", params).fetchone()[0]
    rows = connection.execute(f"{sql} LIMIT ? OFFSET ?", (*params, page.limit, page.offset)).fetchall()
    return {key: [dict(row) for row in rows], "total": total, "limit": page.limit, "offset": page.offset}
