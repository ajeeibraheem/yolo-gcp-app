from pymongo.errors import OperationFailure
from motor.motor_asyncio import AsyncIOMotorDatabase

async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    # Datasets: unique name
    try:
        await db.datasets.create_index("name", unique=True, name="uq_dataset_name")
    except OperationFailure as e:
        # IndexOptionsConflict (code 85) — drop and recreate with expected name/options
        if e.code == 85:
            await _recreate_index(db, "datasets", [("name", 1)], "uq_dataset_name", unique=True)
        else:
            raise

    # Images: unique per dataset+path
    try:
        await db.images.create_index([("dataset_id", 1), ("image_path", 1)], unique=True, name="uq_image_path_per_dataset")
    except OperationFailure as e:
        if e.code == 85:
            await _recreate_index(db, "images", [("dataset_id", 1), ("image_path", 1)], "uq_image_path_per_dataset", unique=True)
        else:
            raise

async def _recreate_index(db: AsyncIOMotorDatabase, coll: str, keys, name: str, **kwargs):
    info = await db[coll].index_information()
    # Drop any index with same keys but different name/options
    for idx_name, idx in info.items():
        if idx.get("key") == keys and idx_name != name:
            await db[coll].drop_index(idx_name)
    await db[coll].create_index(keys, name=name, **kwargs)
