import logging
from sqlalchemy.future import select
from src.db.models import AsyncSessionLocal, RequestDB
from src.models.request import RequestStatus
from src.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

class RequestService:
    def __init__(self, notification_service: NotificationService = None):
        self.notification_service = notification_service

    async def create_request(self, beneficiary_id: str, category: str, description: str, address: str, scheduled_time: str, phone: str = ""):
        try:
            async with AsyncSessionLocal() as session:
                new_request = RequestDB(
                    beneficiary_id=beneficiary_id,
                    category=category,
                    description=description,
                    address=address,
                    scheduled_time=scheduled_time,
                    phone=phone,
                    status=RequestStatus.NEW.value
                )
                session.add(new_request)
                await session.commit()
                await session.refresh(new_request)

                # Уведомляем волонтеров
                if self.notification_service:
                    msg = (f"🔔 Новая заявка #{new_request.id}!\n"
                           f"Категория: {new_request.category}\n"
                           f"Адрес: {new_request.address}\n"
                           f"Время: {new_request.scheduled_time}")
                    await self.notification_service.notify_volunteers(msg, request_id=new_request.id)

                return new_request
        except Exception as e:
            logger.exception(f"Error creating request: {e}")
            raise

    async def get_new_requests(self):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(RequestDB).filter(
                    RequestDB.status == RequestStatus.NEW.value
                )
            )
            return result.scalars().all()

    async def get_active_requests(self):
        """Получить активные заявки (новые и принятые, без отменённых)."""
        from sqlalchemy import or_
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(RequestDB).filter(
                    or_(
                        RequestDB.status == RequestStatus.NEW.value,
                        RequestDB.status == RequestStatus.ACCEPTED.value
                    )
                )
            )
            return result.scalars().all()

    async def accept_request(self, request_id: int, volunteer_id: str):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(RequestDB).filter(RequestDB.id == request_id, RequestDB.status == RequestStatus.NEW.value)
            )
            request = result.scalar_one_or_none()
            if request:
                request.status = RequestStatus.ACCEPTED.value
                request.volunteer_id = volunteer_id
                await session.commit()
                return request
            return None

    async def complete_request(self, request_id: int):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(RequestDB).filter(RequestDB.id == request_id, RequestDB.status == RequestStatus.ACCEPTED.value)
            )
            request = result.scalar_one_or_none()
            if request:
                request.status = RequestStatus.COMPLETED.value
                await session.commit()
                return request
            return None

    async def get_request_by_id(self, request_id: int):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(RequestDB).filter(RequestDB.id == request_id)
            )
            return result.scalar_one_or_none()

    async def get_user_requests(self, user_id: str):
        """Получить все заявки пользователя."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(RequestDB).filter(RequestDB.beneficiary_id == str(user_id))
            )
            return result.scalars().all()

    async def cancel_request(self, request_id: int):
        """Отменить заявку (для пользователя)."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(RequestDB).filter(RequestDB.id == request_id)
            )
            request = result.scalar_one_or_none()
            if request:
                request.status = RequestStatus.CANCELLED.value
                await session.commit()
                return request
            return None
