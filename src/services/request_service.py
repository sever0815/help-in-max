from sqlalchemy.future import select
from src.db.models import AsyncSessionLocal, RequestDB
from src.models.request import RequestStatus
from src.services.notification_service import NotificationService

class RequestService:
    def __init__(self, notification_service: NotificationService = None):
        self.notification_service = notification_service

    async def create_request(self, beneficiary_id: str, category: str, description: str, address: str, scheduled_time: str):
        async with AsyncSessionLocal() as session:
            new_request = RequestDB(
                beneficiary_id=beneficiary_id,
                category=category,
                description=description,
                address=address,
                scheduled_time=scheduled_time,
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
                await self.notification_service.notify_volunteers(msg)
            
            return new_request

    async def get_new_requests(self):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(RequestDB).filter(RequestDB.status == RequestStatus.NEW.value)
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
