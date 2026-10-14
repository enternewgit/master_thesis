from decouple import config
from typing import Union
from fastapi import HTTPException
import motor.motor_asyncio
from pymongo import errors, DESCENDING
from bson import ObjectId
from word_haku_api.schemas import EEGsv2Body, FoldersBody, TrainIdsv2, TrainIdsv2Body
from typing import List
from word_haku_api.auth_utils import AuthJwtCsrf
from typing import Optional
from datetime import datetime, timedelta, timezone
from motor.motor_asyncio import AsyncIOMotorGridFSBucket, AsyncIOMotorCollection

MONGO_API_KEY = config("MONGO_API_KEY")

client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_API_KEY)
db = client.word_haku
collection_eegs = db.eegs
collection_users = db.users
collection_counter = db.counter
collection_folders = db.folders
collection_eegsv2 = db.eegs_v2
collection_counterv2 = db.counter_v2
collection_models = db.models
auth = AuthJwtCsrf()


# EEGs_v2のシリアライザ
def eegs_serializer(eegs_list: List[dict]) -> List[dict]:
    return [
        {
            "id": str(eegs["_id"]),
            "train_id": str(eegs["train_id"]),
            "timestamps": eegs["timestamps"],
            "eegs": eegs["eegs"],
            "words": eegs.get("words"),
            "eventMarker": eegs.get("eventMarker"),
        }
        for eegs in eegs_list
    ]

def users_searializer(users) -> dict:
    return {
        "id": str(users["_id"]),
        "username": users["username"],
        "login_id": users["login_id"],
        "role": users.get("role", "user"),
    }


def ids_serializer(ids) -> dict:
    return {
        "id": str(ids["_id"]),
        "login_id": ids["login_id"],
        "created_at": str(ids["created_at"]),
        "Folder": ids.get("Folder"),
        "expInfo": ids.get("expInfo"),
        "eegSettings": ids.get("eegSettings"),
        "Memo": ids.get("Memo"),
    }


async def folders_serializer(folders: List[dict]) -> List[dict]:
    if not folders:
        return []
    # Batch count: get all folder item counts in one aggregation query
    login_id = folders[0]["login_id"]
    folder_names = [f["name"] for f in folders]
    pipeline = [
        {"$match": {"login_id": login_id, "Folder": {"$in": folder_names}}},
        {"$group": {"_id": "$Folder", "count": {"$sum": 1}}},
    ]
    counts_cursor = collection_counterv2.aggregate(pipeline)
    counts_map = {}
    async for doc in counts_cursor:
        counts_map[doc["_id"]] = doc["count"]

    serialized = []
    for folder in folders:
        serialized.append({
            "id": str(folder["_id"]),
            "login_id": folder["login_id"],
            "name": folder["name"],
            "created_at": str(folder["created_at"]),
            "item_count": counts_map.get(folder["name"], 0)
        })
    return serialized

def models_serializer(models)-> List[dict]:
    return [
        {
            "id": str(model["_id"]),
            "login_id": model.get("login_id"),
            "train_id": model.get("train_id"),
            "name": model.get("name"),
            "note": model.get("note"),
            "hyperparameters": model.get("hyperparameters"),
            "input_shape": model.get("input_shape"),
            "output_labels": model.get("output_labels"),
            "label_policy": model.get("label_policy"),
            "created_at": str(model.get("created_at")),
            "updated_at": str(model.get("updated_at")),
            "model_file_id": str(model.get("model_file_id")),
            "label_encoder_file_id": str(model.get("label_encoder_file_id")),
        }
        for model in models
    ]


# Create of Counterv2
async def db_create_train(login_id, settings: TrainIdsv2Body) -> dict:
    now_utc = datetime.now(timezone.utc)
    now_jst = now_utc + timedelta(hours=9)
    formatted_time = now_jst.strftime("%Y-%m-%dT%H:%M:%S")
    train_data = {
        "login_id": login_id,
        "created_at": formatted_time,
        **settings.model_dump(exclude_none=True),  # `None` の値を省略
    }
    # MongoDB に挿入
    result = await collection_counterv2.insert_one(train_data)

    return result.inserted_id


# Create of EEGsv2
async def db_create_eegs(data: EEGsv2Body, train_id):
    eegs = {"train_id": ObjectId(train_id), **data.model_dump(exclude_none=True)}
    result = await collection_eegsv2.insert_one(eegs)

    return result.inserted_id


# Update of Counterv2
async def db_update_train(settings: TrainIdsv2Body, train_id) -> int:
    train_data = settings.model_dump(exclude_none=True)

    # ドキュメントを更新
    query = {"_id": ObjectId(train_id)}
    update_operation = {"$set": train_data}
    result = await collection_counterv2.update_one(query, update_operation)

    # 更新されたドキュメントの数を返す
    return result.modified_count


# Delete of only Counterv2
async def db_delete_train(train_id: str) -> bool:
    deleted_id = await collection_counterv2.delete_one({"_id": ObjectId(train_id)})

    if deleted_id.deleted_count != 1:
        return False  # Counterが削除できなかったら失敗

    # EEGsが存在しなくてもOK
    await collection_eegsv2.delete_many({"train_id": ObjectId(train_id)})
    return True


# Delete of Counterv2 and related EEGsv2
async def db_delete_train_and_eegs(train_ids: List[str]) -> bool:
    object_ids = [ObjectId(train_id) for train_id in train_ids]
    eegs = await collection_eegsv2.find({"train_id": {"$in": object_ids}}).to_list(
        length=None
    )
    if eegs:
        deleted_eegs = await collection_eegsv2.delete_many(
            {"train_id": {"$in": object_ids}}
        )
        deleted_ids = await collection_counterv2.delete_many(
            {"_id": {"$in": object_ids}}
        )
        if deleted_eegs.deleted_count > 0 and deleted_ids.deleted_count > 0:
            return deleted_ids.deleted_count
    # EEGsが存在しない場合はCounterのみ削除
    deleted_ids = await collection_counterv2.delete_many({"_id": {"$in": object_ids}})
    if deleted_ids.deleted_count > 0:
        return deleted_ids.deleted_count
    return False


# Read user's Counterv2 list
async def db_get_train_ids(login_id: str) -> List[dict]:
    train_ids = await collection_counterv2.find({"login_id": login_id}).to_list(
        length=None
    )
    ids = []
    for train_id in train_ids:
        ids.append(ids_serializer(train_id))
    return ids


# Read EEGsv2 data by train_id
async def db_get_eegs_by_train_id(login_id: str, train_id: str) -> List[dict]:
    # 自分の train_id かを確認
    train_doc = await collection_counterv2.find_one({
        "_id": ObjectId(train_id),
        "login_id": login_id
    })
    if not train_doc:
        raise HTTPException(status_code=403, detail="Access denied to this train_id")

    eegs = await collection_eegsv2.find({
        "train_id": ObjectId(train_id)
    }).to_list(length=None)

    return eegs_serializer(eegs) if eegs else []


async def db_get_eegs_by_multi_train_id(login_id: str, train_ids: List[str]) -> List[dict]:
    try:
        object_ids = [ObjectId(tid) for tid in train_ids]
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid train_id format")

    train_docs = await collection_counterv2.find({
        "_id": {"$in": object_ids},
        "login_id": login_id
    }).to_list(length=None)

    # 不一致があればアクセス拒否
    if not train_docs or len(train_docs) != len(object_ids):
        raise HTTPException(status_code=403, detail="Some train_ids are not owned by user")

    eegs = await collection_eegsv2.find({
        "train_id": {"$in": object_ids}
    }).to_list(length=None)

    return eegs_serializer(eegs) if eegs else []


# 保留Read user's specific word EEGs data of EEGsv2
# async def db_get_eegs_by_login_id_and_word(login_id: str, word: str, trainIds: List[ObjectId]) -> Union[List[dict], bool]:
#     valid_train_ids = []
#     for tid in trainIds:
#         train_doc = await collection_counter.find_one({"_id": tid})
#         if train_doc and train_doc["login_id"] == login_id:
#             valid_train_ids.append(tid)
#     if not valid_train_ids:
#         return False
#     query = {"train_id": {"$in": valid_train_ids}}
#     if word:
#         query["word"] = word
#     eegs = await collection_eegs.find(query).to_list(length=None)
#     if eegs:
#         return eegs_serializer(eegs)
#     return False


async def db_signup(data: dict) -> dict:
    username = data.get("username")
    login_id = data.get("login_id")
    password = data.get("password")
    if not password or len(password) < 8:
        raise HTTPException(
            status_code=400, detail="Password must be at least 8 characters long."
        )
    user = await collection_users.insert_one(
        {
            "username": username,
            "login_id": login_id,
            "password": auth.generate_hashed_pw(password),
            "role": "user",
        }
    )
    new_user = await collection_users.find_one({"_id": user.inserted_id})
    return users_searializer(new_user)


async def db_login(data: dict) -> str:
    login_id = data.get("login_id")
    password = data.get("password")
    user = await collection_users.find_one({"login_id": login_id})
    if not user or not auth.verify_pw(password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid login_id or password")
    role = user.get("role", "user")
    token = auth.encode_jwt(user["login_id"], role)
    return token


async def db_OAuth_login(login_id: str) -> str:
    user = await collection_users.find_one({"login_id": login_id})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid login_id")
    token = auth.encode_jwt(user["login_id"])
    return token


async def db_get_username_by_login_id(login_id: str) -> Optional[dict]:
    user = await collection_users.find_one({"login_id": login_id})
    if user:
        return {
            "login_id": user["login_id"],
            "username": user["username"],
            "role": user.get("role", "user"),
        }
    return None


# フォルダーを作成
async def db_create_folder(login_id: str, folder: FoldersBody) -> bool:
    # now_utc = datetime.utcnow()
    now_utc = datetime.now(timezone.utc)
    now_jst = now_utc + timedelta(hours=9)
    formatted_time = now_jst.strftime("%Y-%m-%dT%H:%M:%S")
    if await db_exist_folder(login_id, folder.name):
        return False
    folder = await collection_folders.insert_one(
        {
            "login_id": login_id,
            "name": folder.name,
            "created_at": formatted_time,
        }
    )
    if folder:
        return True


# フォルダー一覧を取得
async def db_get_folders(login_id: str) -> List[dict]:
    folders = (
        await collection_folders.find({"login_id": login_id})
        .sort("created_at", DESCENDING)
        .to_list(length=None)
    )
    if folders:
        return await folders_serializer(folders)
    return []


# 当該名称のフォルダが既に存在するか確認
async def db_exist_folder(login_id: str, name: str) -> bool:
    folder = await collection_folders.find_one({"login_id": login_id, "name": name})
    if folder or name == "ALL":
        return True
    return False


# フォルダーに格納されているTrainIdsを取得
async def db_get_train_ids_by_folder(login_id: str, folder_name: str) -> List[dict]:
    folder = await collection_folders.find_one(
        {"login_id": login_id, "name": folder_name}
    )
    if not folder and folder_name != "ALL":
        return []
    if folder_name == "ALL":
        train_ids = (
            await collection_counterv2.find({"login_id": login_id})
            .sort("created_at", DESCENDING)
            .to_list(length=None)
        )
    else:
        train_ids = (
            await collection_counterv2.find(
                {"login_id": login_id, "Folder": folder_name}
            )
            .sort("created_at", DESCENDING)
            .to_list(length=None)
        )

    train_ids = [ids_serializer(train_id) for train_id in train_ids]
    # print(train_ids)
    if train_ids:
        return train_ids
    return []


# フォルダー追加
async def db_add_tag_to_eegs(login_id: str, train_ids: List[str], tag: str) -> bool:
    object_ids = [ObjectId(train_id) for train_id in train_ids]

    try:
        for train_id in object_ids:
            document = await collection_counterv2.find_one({"_id": train_id})
            if document and not isinstance(document.get("Folder"), list):

                await collection_counterv2.update_one(
                    {"_id": train_id},
                    {"$set": {"Folder": [document.get("Folder")]}},
                )
        # 既にタグが存在する場合は，追加しない
        updated = await collection_counterv2.update_many(
            {"_id": {"$in": object_ids}, "Folder": {"$ne": tag}},
            {"$push": {"Folder": tag}},
        )

        return updated.modified_count > 0

    except errors.WriteError as e:
        print(f"WriteError: {e.details}")
        return False


# タグ（フォルダー所属）削除
async def db_delete_tag_to_eegs(
    login_id: str, train_ids: List[str], tag: str, delete: bool = False
) -> bool:
    object_ids = [ObjectId(train_id) for train_id in train_ids]
    updated = await collection_counterv2.update_many(
        {"_id": {"$in": object_ids}}, {"$pull": {"Folder": tag}}
    )
    if updated.modified_count > 0:
        if delete:
            await collection_counterv2.update_many(
                {"_id": {"$in": object_ids}, "Folder": []}, {"$unset": {"Folder": ""}}
            )
        return True
    return False


# フォルダー移動
async def db_move_trainids(
    login_id: str, folder_name: str, train_ids: List[str]
) -> bool:
    folder = await db_exist_folder(login_id, folder_name)
    if not folder:
        return False
    object_ids = [ObjectId(train_id) for train_id in train_ids]
    updated = await collection_counterv2.update_many(
        {"_id": {"$in": object_ids}}, {"$set": {"folder": folder_name}}
    )
    if updated.modified_count > 0:
        return True
    return False


# フォルダー名前変更
async def db_rename_folder(login_id: str, old_name: str, new_name: str) -> bool:
    folder = await collection_folders.find_one({"login_id": login_id, "name": old_name})
    if not folder:
        return False
    exist = await db_exist_folder(login_id, new_name)
    if exist:
        return False
    updated = await collection_folders.update_one(
        {"_id": folder["_id"]}, {"$set": {"name": new_name}}
    )
    update_counter = await collection_counterv2.update_many(
        {"login_id": login_id, "folder": old_name},
        {"$set": {"folder.$[elem]": new_name}},
        array_filters=[{"elem": old_name}],
    )
    if updated.modified_count > 0 and update_counter.modified_count > 0:
        return True
    return False


# フォルダー削除（中身が存在する場合は，削除不可）
async def db_delete_folder(login_id: str, name: str) -> bool:
    folder = await collection_folders.find_one({"login_id": login_id, "name": name})
    if not folder:
        return False
    train_ids = await collection_counterv2.find(
        {"login_id": login_id, "folder": name}
    ).to_list(length=None)
    if train_ids:
        return False
    deleted = await collection_folders.delete_one({"_id": folder["_id"]})
    if deleted.deleted_count > 0:
        return True
    return False

# 空フォルダ一括削除
async def db_delete_empty_folders(login_id: str) -> bool:
    folders = await collection_folders.find({"login_id": login_id}).to_list(length=None)
    train_docs = await collection_counterv2.find({"login_id": login_id}, {"Folder": 1}).to_list(length=None)
    
    used_folders = set()
    for doc in train_docs:
        folder_field = doc.get("Folder")
        if isinstance(folder_field, list):
            used_folders.update(folder_field)
        elif isinstance(folder_field, str):
            used_folders.add(folder_field)
    
    unused_folders = [
        f for f in folders
        if f["name"] != "ALL" and f["name"] not in used_folders
    ]
    if unused_folders:
        unused_names = [f["name"] for f in unused_folders]
        result = await collection_folders.delete_many(
            {"login_id": login_id, "name": {"$in": unused_names}}
        )
        if result.deleted_count > 0:
            return True
    return False

async def db_change_profile(login_id: str, new_name: str) -> bool:
    updated = await collection_users.update_one(
        {"login_id": login_id}, {"$set": {"username": new_name}}
    )
    if updated.modified_count > 0:
        return True
    return False


async def db_change_password(
    login_id: str, current_password: str, new_password: str
) -> str:
    user = await collection_users.find_one({"login_id": login_id})
    if not user or not auth.verify_pw(current_password, user["password"]):
        return "incorrect"

    updated = await collection_users.update_one(
        {"login_id": login_id},
        {"$set": {"password": auth.generate_hashed_pw(new_password)}},
    )

    if updated.modified_count > 0:
        return "success"

    return "failed"

# EEGデータPOST時のフォルダー作成処理
async def db_create_folder_for_eeg(login_id: str, folders: List[str]) -> bool:
    now_utc = datetime.now(timezone.utc)
    now_jst = now_utc + timedelta(hours=9)
    formatted_time = now_jst.strftime('%Y-%m-%dT%H:%M:%S')
    for folder in folders:
        if await db_exist_folder(login_id, folder):
            continue
        await collection_folders.insert_one({
            "login_id": login_id,
            "name": folder,
            "created_at": formatted_time,
        })
    return True

# 推論モデル一覧取得
async def db_get_models(login_id: str) -> List[dict]:
    models = await collection_models.find({"login_id": login_id}).to_list(length=None)
    if models:
        return models_serializer(models)
    return []

# 単一の推論モデル取得
async def db_get_model_by_id(model_id: str, login_id:str) -> Optional[dict]:
    model = await collection_models.find_one({"_id": ObjectId(model_id), "login_id": login_id})
    if model:
        return models_serializer([model])[0]
    return None

# 複数推論モデル削除
async def db_delete_models(model_ids: List[str], login_id: str) -> bool:
    object_ids = [ObjectId(model_id) for model_id in model_ids]
    models_to_delete = await collection_models.find(
        {"_id": {"$in": object_ids}, "login_id": login_id}
    ).to_list(length=None)
    model_file_ids = [model["model_file_id"] for model in models_to_delete if "model_file_id" in model]
    label_encoder_file_ids = [model["label_encoder_file_id"] for model in models_to_delete if "label_encoder_file_id" in model]
    
    for model_file_id in model_file_ids:
        try:
            gridfs_bucket = AsyncIOMotorGridFSBucket(db)
            await gridfs_bucket.delete(model_file_id)
        except errors.GridFSFileNotFound:
            print(f"File with ID {model_file_id} not found in GridFS.")
    
    for label_encoder_file_id in label_encoder_file_ids:
        try:
            gridfs_bucket = AsyncIOMotorGridFSBucket(db)
            await gridfs_bucket.delete(label_encoder_file_id)
        except errors.GridFSFileNotFound:
            print(f"File with ID {label_encoder_file_id} not found in GridFS.")
    
    deleted = await collection_models.delete_many(
        {"_id": {"$in": object_ids}, "login_id": login_id}
    )
    if deleted.deleted_count > 0:
        return True
    return False

## 管理者用機能

# ユーザ一覧取得
async def db_get_users(login_id: str) -> List[dict]:
    admin_info = await db_get_username_by_login_id(login_id)
    # 管理者権限を持つことをDB参照で確認
    if not admin_info or admin_info.get("role") != "admin":
        return []
    users = await collection_users.find().to_list(length=None)
    if users:
        return [users_searializer(user) for user in users]
    return []

# 他ユーザのフォルダ一覧取得
async def db_get_folders_other(login_id:str, target_login_id: str) -> List[dict]:
    admin_info = await db_get_username_by_login_id(login_id)
    # 管理者権限を持つことをDB参照で確認
    if not admin_info or admin_info.get("role") != "admin":
        return []
    folders = await collection_folders.find({"login_id": target_login_id}).sort("created_at", DESCENDING).to_list(length=None)
    if folders:
        return await folders_serializer(folders)
    return []

# 他ユーザのカウンタ一覧を取得
async def db_get_train_ids_by_folder_other(login_id: str, target_login_id: str, folder_name: str) -> List[dict]:
    admin_info = await db_get_username_by_login_id(login_id)
    # 管理者権限を持つことをDB参照で確認
    if not admin_info or admin_info.get("role") != "admin":
        return []
    if folder_name == "ALL":
        train_ids = await collection_counterv2.find({"login_id": target_login_id}).to_list(length=None)
    else:
        train_ids = await collection_counterv2.find({"login_id": target_login_id, "Folder": folder_name}).to_list(length=None)
    
    train_ids = [ids_serializer(train_id) for train_id in train_ids]
    if train_ids:
        return train_ids
    return []

# 他ユーザのEEGデータを取得
async def db_get_eegs_by_multi_train_ids_other(
    login_id: str, train_ids: List[str]
) -> List[dict]:
    admin_info = await db_get_username_by_login_id(login_id)
    # 管理者権限を持つことをDB参照で確認
    if not admin_info or admin_info.get("role") != "admin":
        print("Access denied: Not an admin user")
        return []
    
    object_ids = [ObjectId(tid) for tid in train_ids]
    eegs = await collection_eegsv2.find({
        "train_id": {"$in": object_ids}
    }).to_list(length=None)
    
    if eegs:
        return eegs_serializer(eegs)
    return []

def get_db():
    return db