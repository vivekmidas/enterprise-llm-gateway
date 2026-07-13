from app.services.job_service import JobService


class JobProgress:

    def __init__(
        self,
        service: JobService,
        job_id: int,
    ):
        self.service = service
        self.job_id = job_id

    async def __aenter__(self):
        await self.service.start(self.job_id)
        return self

    async def __aexit__(self, exc_type, exc, tb):

        if exc:
            await self.service.fail(
                self.job_id,
                str(exc),
            )
            return False

        await self.service.complete(self.job_id)

    async def update(
        self,
        progress: int,
        message: str,
    ):
        await self.service.update_progress(
            self.job_id,
            progress,
            message,
        )

    async def complete(
        self,
        message="Completed",
    ):
        await self.service.complete(
            self.job_id,
            message,
        )

    async def fail(
        self,
        error: str,
    ):
        await self.service.fail(
            self.job_id,
            error,
        )