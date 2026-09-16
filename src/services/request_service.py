from typing import List, Dict, Optional
from src.models.request import Request, RequestStatus
from datetime import datetime

class RequestService:
    def __init__(self):
        # Временное хранилище в памяти до подключения БД
        self._requests: Dict[int, Request] = {}
        self._counter = 1

    async def create_request(self, beneficiary_id: str, category: str, description: str, address: str) -> Request:
        request = Request(
            id=self._counter,
            beneficiary_id=beneficiary_id,
            category=category,
            description=description,
            address=address,
            status=RequestStatus.NEW
        )
        self._requests[self._counter] = request
        self._counter += 1
        return request

    async def get_new_requests(self) -> List[Request]:
        return [r for r in self._requests.values() if r.status == RequestStatus.NEW]

    async def accept_request(self, request_id: int, volunteer_id: str) -> Optional[Request]:
        request = self._requests.get(request_id)
        if request and request.status == RequestStatus.NEW:
            request.status = RequestStatus.ACCEPTED
            request.volunteer_id = volunteer_id
            request.updated_at = datetime.now()
            return request
        return None

    async def complete_request(self, request_id: int) -> Optional[Request]:
        request = self._requests.get(request_id)
        if request and request.status == RequestStatus.ACCEPTED:
            request.status = RequestStatus.COMPLETED
            request.updated_at = datetime.now()
            return request
        return None

    async def get_request_by_id(self, request_id: int) -> Optional[Request]:
        return self._requests.get(request_id)
