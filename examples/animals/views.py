from bson import ObjectId
from fastapi import Body, Depends, HTTPException, Path, Query, status
from fastapi.routing import APIRouter
from models import Animal, AnimalReader, AnimalWriter

router = APIRouter(prefix="/animals")


async def get_animal_by_id(animal_id: str = Path(regex=r"^[a-f0-9]{24}$")) -> Animal:
    try:
        return await Animal.objects.get(_id=ObjectId(animal_id))
    except Animal.DocumentNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Animal not found")


@router.post("", status_code=status.HTTP_201_CREATED)
async def animal_create(animal: AnimalWriter = Body(...)) -> AnimalReader:
    return await Animal(**animal.model_dump()).commit()


@router.get("/{animal_id}")
async def animal_retrieve(animal: Animal = Depends(get_animal_by_id)) -> AnimalReader:
    return animal


@router.patch("/{animal_id}")
async def animal_partial_update(
    animal: Animal = Depends(get_animal_by_id),
    update: AnimalWriter = Body(...),
) -> AnimalReader:
    animal.update(update.model_dump(exclude_unset=True))
    await animal.save()
    return animal


@router.put("/{animal_id}")
async def animal_full_update(
    animal: Animal = Depends(get_animal_by_id),
    updater: AnimalWriter = Body(...),
) -> AnimalReader:
    animal.update(updater.model_dump())
    await animal.save()
    return animal


@router.get("")
async def animal_list(names: list[str] | None = Query(alias="name")) -> list[AnimalReader]:
    animals = Animal.objects
    if names:
        animals = animals.filter(name__in=names)
    return await animals.all()
