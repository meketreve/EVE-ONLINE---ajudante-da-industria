"""
Fila de jobs assíncrona em memória (sem Redis).

Garante:
  - Deduplicação por job_id (mesmo job não entra duas vezes)
  - Concurrency configurável por fila
  - Tratamento de erros sem derrubar o worker
  - Reinicialização limpa: jobs perdidos no restart são re-enfileirados
    pelo scheduler periódico
"""

import asyncio
import logging
from typing import Callable, Any, Coroutine

logger = logging.getLogger(__name__)


class JobRunner:
    def __init__(self, name: str, concurrency: int = 2):
        self.name        = name
        self.concurrency = concurrency
        self._queue:       asyncio.Queue                         = asyncio.Queue()
        self._in_progress: set[str]                              = set()
        self._worker_tasks: list[asyncio.Task]                   = []

    def start(self) -> None:
        """Inicia os workers. Chamar uma vez no startup da app."""
        for i in range(self.concurrency):
            task = asyncio.create_task(self._worker(i), name=f"{self.name}-worker-{i}")
            self._worker_tasks.append(task)
        logger.info("[%s] %d worker(s) iniciado(s).", self.name, self.concurrency)

    async def stop(self) -> None:
        """Aguarda a fila esvaziar e cancela workers."""
        await self._queue.join()
        for task in self._worker_tasks:
            task.cancel()
        self._worker_tasks.clear()

    async def enqueue(
        self,
        job_id: str,
        fn: Callable[..., Coroutine[Any, Any, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> bool:
        """
        Adiciona um job à fila.
        Retorna False se o job_id já está em andamento (deduplicação).
        """
        if job_id in self._in_progress:
            logger.debug("[%s] job '%s' ignorado — já em andamento.", self.name, job_id)
            return False
        await self._queue.put((job_id, fn, args, kwargs))
        self._in_progress.add(job_id)
        logger.debug("[%s] job '%s' enfileirado (fila=%d).", self.name, job_id, self._queue.qsize())
        return True

    async def _worker(self, worker_id: int) -> None:
        while True:
            job_id, fn, args, kwargs = await self._queue.get()
            logger.info("[%s] worker-%d executando '%s'.", self.name, worker_id, job_id)
            try:
                await fn(*args, **kwargs)
                logger.info("[%s] worker-%d concluiu '%s'.", self.name, worker_id, job_id)
            except Exception as exc:
                logger.error(
                    "[%s] worker-%d falhou em '%s': %s",
                    self.name, worker_id, job_id, exc, exc_info=True,
                )
            finally:
                self._in_progress.discard(job_id)
                self._queue.task_done()


# ── Instâncias globais ────────────────────────────────────────────────────────
# Iniciadas no startup da app (main.py lifespan)

discovery_runner = JobRunner("discovery", concurrency=3)
crawl_runner     = JobRunner("crawl",     concurrency=2)
