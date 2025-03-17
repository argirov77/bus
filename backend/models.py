from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional

# --- Модели для Stop ---
class StopBase(BaseModel):
    stop_name: str

class StopCreate(StopBase):
    pass

class Stop(StopBase):
    id: int
    class Config:
        from_attributes = True  # для Pydantic v2 (для v1  orm_mode = True)

# --- Модели для Route ---
class RouteBase(BaseModel):
    name: str

class RouteCreate(RouteBase):
    pass

class Route(RouteBase):
    id: int
    class Config:
        from_attributes = True

# --- Модели для RouteStop ---
class RouteStopBase(BaseModel):
    route_id: int
    stop_id: int
    order: int
    arrival_time: Optional[datetime] = None
    departure_time: Optional[datetime] = None

class RouteStopCreate(RouteStopBase):
    pass

class RouteStop(RouteStopBase):
    id: int
    class Config:
        from_attributes = True

# --- Модели для Pricelist ---
class PricelistBase(BaseModel):
    name: str

class PricelistCreate(PricelistBase):
    pass

class Pricelist(PricelistBase):
    id: int
    class Config:
        from_attributes = True

# --- Модели для Prices ---
class PricesBase(BaseModel):
    pricelist_id: int
    departure_stop_id: int
    arrival_stop_id: int
    price: float

class PricesCreate(PricesBase):
    pass

class Prices(PricesBase):
    id: int
    class Config:
        from_attributes = True

# --- Модели для Tour ---
class TourBase(BaseModel):
    route_id: int
    pricelist_id: int
    date: date
    seats: int

class TourCreate(TourBase):
    pass

class Tour(TourBase):
    id: int
    class Config:
        from_attributes = True

# --- Модели для Passenger ---
class PassengerBase(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None

class PassengerCreate(PassengerBase):
    pass

class Passenger(PassengerBase):
    id: int
    class Config:
        from_attributes = True

# --- Модели для Ticket ---
class TicketBase(BaseModel):
    tour_id: int
    seat_id: int
    passenger_id: int
    departure_stop_id: int
    arrival_stop_id: int

class TicketCreate(TicketBase):
    pass

class Ticket(TicketBase):
    id: int
    class Config:
        from_attributes = True

# --- Модели для Available ---
class AvailableBase(BaseModel):
    tour_id: int
    departure_stop_id: int
    arrival_stop_id: int
    seats: int

class AvailableCreate(AvailableBase):
    pass

class Available(AvailableBase):
    id: int
    class Config:
        from_attributes = True

# --- Модели для Seat ---
class SeatBase(BaseModel):
    tour_id: int
    seat_num: int
    available: str  

class SeatCreate(SeatBase):
    pass

class Seat(SeatBase):
    id: int
    class Config:
        from_attributes = True
