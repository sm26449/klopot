"""Pydantic API I/O schemas (DTOs).

Each module mirrors a resource. Pattern per resource:

    class XxxBase(BaseModel):
        # fields shared by Create / Update / Read

    class XxxCreate(XxxBase):
        # fields required at create time

    class XxxUpdate(BaseModel):
        # all fields optional for PATCH

    class XxxRead(XxxBase):
        # output shape (includes id, timestamps)
        model_config = ConfigDict(from_attributes=True)

This separation keeps the API contract independent from the ORM
column definitions — we can rename columns or add internal fields
without breaking clients.
"""
