"""The one page / page_size pair of every paged list. The page number is capped: a huge one
overflows the SQL OFFSET (a 500), and no real list has 100 000 pages."""

from typing import Annotated

from fastapi import Query

MAX_PAGE = 100_000

Page = Annotated[int, Query(ge=1, le=MAX_PAGE)]
PageSize = Annotated[int, Query(ge=1, le=100)]
