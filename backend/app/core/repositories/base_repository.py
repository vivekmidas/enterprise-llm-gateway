from typing import Generic, TypeVar

T = TypeVar("T")

class BaseRepository(Generic[T]):

    async def get(self):
        pass

    async def create(self):
        pass

    async def update(self):
        pass

    async def delete(self):
        pass

    async def list(self):
        pass