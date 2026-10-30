from fastapi import Request


async def get_conn(request: Request):
    # The pool uses autocommit, so each statement commits on its own.
    # Multi-statement work must open `async with conn.transaction():` explicitly.
    async with request.app.state.pool.connection() as conn:
        yield conn
