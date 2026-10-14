from decouple import config
from typing import Union
from fastapi import HTTPException
import motor.motor_asyncio
from pymongo import errors, DESCENDING
from bson import ObjectId
from word_haku_api.schemas import EEGsBody, EEGsv2Body,TrainIdsBody, FoldersBody
from typing import List
from word_haku_api.auth_utils import AuthJwtCsrf
from typing import Optional
from datetime import datetime, timezone,timedelta

MONGO_API_KEY = config('MONGO_API_KEY')

client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_API_KEY)
db = client.word_haku
collection_eegs = db.eegs
collection_users = db.users
collection_counter = db.counter
collection_folders = db.folders
collection_eegsv2 = db.eegs_v2
auth = AuthJwtCsrf()

def eegs_serializer(eegs) -> List[dict]:
    return [
        {
            "id": str(eeg["_id"]),
            #"login_id": eeg["login_id"],
            "train_id": str(eeg["train_id"]),
            "timestamp": eeg["timestamp"],
            "data_0": eeg["data_0"],
            "data_1": eeg["data_1"],
            "data_2": eeg["data_2"],
            "data_3": eeg["data_3"],
            "word": eeg["word"]
        }
        for eeg in eegs
    ]
    
#EEGs_v2のシリアライザ
def eegs_v2_serializer(eegs) -> dict:
    return {
        "id": str(eegs["_id"]),
        "train_id": str(eegs["train_id"]),
        "timestamps": eegs["timestamps"],
        "eegs": eegs["eegs"],
        "words": eegs.get("words"),
        "eventMarker": eegs.get("eventMarker"),
    }

def users_searializer(users) -> dict:
    return {
        "id": str(users["_id"]),
        "username": users["username"],
        "login_id": users["login_id"],
    }

def ids_serializer(ids) -> dict:
    return {
        "id": str(ids["_id"]),
        "login_id": ids["login_id"],
        "created_at": str(ids["created_at"]),
        "Folder": ids.get("Folder"),
        "words": ids.get("words"),
        "inputWords": ids.get("inputWords"),
        "isShuffle": ids.get("isShuffle"),
        "Duration": ids.get("Duration"),
        "Interval": ids.get("Interval"),
        "NotchFilter": ids.get("NotchFilter"),
        "NotchFilterFrequency": ids.get("NotchFilterFrequency"),
        "BandpassFilter": ids.get("BandpassFilter"),
        "cutOffLow": ids.get("cutOffLow"),
        "cutOffHigh": ids.get("cutOffHigh"),
        "FFT": ids.get("FFT"),
        "DeviceName": ids.get("DeviceName"),
        "WordDisplayTime": ids.get("WordDisplayTime"),
        "PauseTime": ids.get("PauseTime"),
        "advanced": ids.get("advanced"),
        "nbChannels": ids.get("nbChannels"),
        "channelNames": ids.get("channelNames"),
    }

def folders_serializer(folders):
    return [
        {
            "id": str(folder["_id"]),
            "login_id": folder["login_id"],
            "name": folder["name"],
            "created_at": str(folder["created_at"]),
        }
        for folder in folders
    ]

async def create_train_id(user_id, settings: TrainIdsBody) -> dict:
    now_utc = datetime.now(timezone.utc)
    now_jst = now_utc + timedelta(hours=9)
    formatted_time = now_jst.strftime('%Y-%m-%dT%H:%M:%S')
    formatted_date = now_jst.strftime('%Y-%m-%d')
    result = await collection_counter.insert_one({
        "login_id": user_id,
        "created_at": formatted_time,
        "Folder": settings.Folder,
        "words": settings.words,
        "inputWords": settings.inputWords,
        "isShuffle": settings.isShuffle,
        "Duration": settings.Duration,
        "Interval": settings.Interval,
        "NotchFilter": settings.NotchFilter,
        "NotchFilterFrequency": settings.NotchFilterFrequency,
        "BandpassFilter": settings.BandpassFilter,
        "cutOffLow": settings.cutOffLow,
        "cutOffHigh": settings.cutOffHigh,
        "FFT": settings.FFT,
        "DeviceName": settings.DeviceName,
        "WordDisplayTime": settings.WordDisplayTime,
        "PauseTime": settings.PauseTime,
        "advanced": settings.advanced,
        "nbChannels": settings.nbChannels,
        "channelNames": settings.channelNames,  
    })
    return result.inserted_id

async def db_create_eegs(data: List[EEGsBody], login_id, settings: TrainIdsBody) -> Union[List[dict], bool]:
    train_id = await create_train_id(login_id, settings)
    for eeg in data:
        eeg["train_id"] = train_id
    await collection_eegs.insert_many([eeg for eeg in data])  

async def db_get_train_ids(login_id: str) -> List[dict]:
    train_ids = await collection_counter.find({"login_id": login_id}).to_list(length=None)
    ids = []
    for train_id in train_ids:
        ids.append(ids_serializer(train_id))
    return ids

async def db_get_eegs_by_login_id_and_word(login_id: str, word: str, trainIds: List[ObjectId]) -> Union[List[dict], bool]:
    # Batch ownership check: fetch all matching train docs at once
    train_docs = await collection_counter.find(
        {"_id": {"$in": trainIds}, "login_id": login_id}
    ).to_list(length=None)
    valid_train_ids = [doc["_id"] for doc in train_docs]
    if not valid_train_ids:
        return False
    query = {"train_id": {"$in": valid_train_ids}}
    if word:
        query["word"] = word   
    eegs = await collection_eegs.find(query).to_list(length=None)
    if eegs:
        return eegs_serializer(eegs)
    return False

async def db_delete_eegs(train_ids: List[str]) -> bool:
    object_ids = [ObjectId(train_id) for train_id in train_ids]
    eegs = await collection_eegs.find({"train_id": {"$in": object_ids}}).to_list(length=None)
    if eegs:
        deleted_eegs = await collection_eegs.delete_many({"train_id": {"$in": object_ids}})
        deleted_ids = await collection_counter.delete_many({"_id": {"$in": object_ids}})
        if deleted_eegs.deleted_count > 0 and deleted_ids.deleted_count > 0:
            return True
    return False

#EEGs_v2のデータ
async def db_create_eegsv2(data: EEGsv2Body, login_id, settings: TrainIdsBody) -> Union[List[dict], bool]:
    train_id = await create_train_id(login_id, settings)
    data["train_id"] = train_id
    await collection_eegs.insert_one(data)  

async def db_signup(data: dict) -> dict:
    username = data.get("username")
    login_id = data.get("login_id")
    password = data.get("password")
    if not password or len(password) < 8:
        raise HTTPException(
            status_code=400, detail="Password must be at least 8 characters long."
        )
    user = await collection_users.insert_one({
        "username": username,
        "login_id": login_id,
        "password": auth.generate_hashed_pw(password)
        })
    new_user = await collection_users.find_one({"_id": user.inserted_id})
    return users_searializer(new_user)

async def db_login(data: dict) -> str:
    login_id = data.get("login_id")
    password = data.get("password")
    user = await collection_users.find_one({"login_id": login_id})
    if not user or not auth.verify_pw(password, user["password"]):
        raise HTTPException(
            status_code=401, detail="Invalid login_id or password"
        )
    role = user.get("role", "user")
    token = auth.encode_jwt(user['login_id'], role)
    return token

async def db_OAuth_login(login_id: str) -> str:
    user = await collection_users.find_one({"login_id": login_id})
    if not user:
        raise HTTPException(
            status_code=401, detail="Invalid login_id"
        )
    role = user.get("role", "user")
    token = auth.encode_jwt(user['login_id'], role)
    return token

async def db_get_username_by_login_id(login_id: str) -> Optional[dict]:
    user = await collection_users.find_one({"login_id": login_id})
    if user:
        return {
            "login_id": user["login_id"],
            "username": user["username"],
        }
    return None

#フォルダーを作成
async def db_create_folder(login_id: str, folder: FoldersBody) -> bool:
    #now_utc = datetime.utcnow()
    now_utc = datetime.now(timezone.utc)
    now_jst = now_utc + timedelta(hours=9)
    formatted_time = now_jst.strftime('%Y-%m-%dT%H:%M:%S')
    if await db_exist_folder(login_id, folder.name):
        return False
    folder = await collection_folders.insert_one({
        "login_id": login_id,
        "name": folder.name,
        "created_at": formatted_time,
    })
    if folder:
        return True

#フォルダー一覧を取得
async def db_get_folders(login_id: str) -> List[dict]:
    #created_atが新しい順に取得
    folders = await collection_folders.find({"login_id": login_id}).sort("created_at", DESCENDING).to_list(length=None)
    if folders:
        return folders_serializer(folders)
    return []

#当該名称のフォルダが既に存在するか確認
async def db_exist_folder(login_id: str, name: str) -> bool:
    folder = await collection_folders.find_one({"login_id": login_id, "name": name})
    if (folder or name == "ALL"):
        return True
    return False

#フォルダーに格納されているTrainIdsを取得
async def db_get_train_ids_by_folder(login_id: str, folder_name: str) -> List[dict]:
    folder = await collection_folders.find_one({"login_id": login_id, "name": folder_name})
    if not folder and folder_name != "ALL":
        return []
    if folder_name == "ALL":
        train_ids = await collection_counter.find({"login_id": login_id}).sort("created_at", DESCENDING).to_list(length=None)
    else:
        train_ids = await collection_counter.find({"login_id":login_id, "Folder": folder_name}).sort("created_at", DESCENDING).to_list(length=None)
    train_ids = [ids_serializer(train_id) for train_id in train_ids]
    if train_ids:
        return train_ids
    return []

#フォルダー追加
async def db_add_tag_to_eegs(login_id: str, train_ids: List[str], tag: str) -> bool:
    object_ids = [ObjectId(train_id) for train_id in train_ids]

    try:
        for train_id in object_ids:
            document = await collection_counter.find_one({"_id": train_id})
            if document and not isinstance(document.get('Folder'), list):

                await collection_counter.update_one(
                    {"_id": train_id},
                    {"$set": {"Folder": [document.get('Folder')]}},
                )
        # 既にタグが存在する場合は，追加しない
        updated = await collection_counter.update_many(
            {"_id": {"$in": object_ids}, "Folder": {"$ne": tag}},
            {"$push": {"Folder": tag}}
        )

        return updated.modified_count > 0

    except errors.WriteError as e:
        print(f"WriteError: {e.details}")
        return False

#タグ（フォルダー所属）削除
async def db_delete_tag_to_eegs(login_id: str, train_ids: List[str], tag: str, delete: bool = False) -> bool:
    object_ids = [ObjectId(train_id) for train_id in train_ids]
    updated = await collection_counter.update_many(
        {"_id": {"$in": object_ids}},
        {"$pull": {"Folder": tag}}
    )
    if updated.modified_count > 0:
        if delete:
            await collection_counter.update_many(
                {"_id": {"$in": object_ids}, "Folder": []},
                {"$unset": {"Folder": ""}}
            )
        return True
    return False

#フォルダー移動
async def db_move_trainids(login_id: str, folder_name: str, train_ids: List[str]) -> bool:
    folder = await db_exist_folder(login_id, folder_name)
    if not folder:
        return False
    object_ids = [ObjectId(train_id) for train_id in train_ids]
    updated = await collection_counter.update_many(
        {"_id": {"$in": object_ids}},
        {"$set": {"Folder": folder_name}}
    )
    if updated.modified_count > 0:
        return True
    return False

#フォルダー名前変更
async def db_rename_folder(login_id: str, old_name: str, new_name: str) -> bool:
    folder = await collection_folders.find_one({"login_id": login_id, "name": old_name})
    if not folder:
        return False
    exist = await db_exist_folder(login_id, new_name)
    if exist:
        return False
    updated = await collection_folders.update_one(
        {"_id": folder["_id"]},
        {"$set": {"name": new_name}}
    )
    update_counter = await collection_counter.update_many(
        {"login_id": login_id, "Folder": old_name},
        {"$set": {"Folder.$[elem]": new_name}},
        array_filters=[{"elem": old_name}]
    )
    if updated.modified_count > 0 and update_counter.modified_count > 0:
        return True
    return False

#フォルダー削除（中身が存在する場合は，削除不可）
async def db_delete_folder(login_id: str, name: str) -> bool:
    folder = await collection_folders.find_one({"login_id": login_id, "name": name})
    if not folder:
        return False
    train_ids = await collection_counter.find({"login_id": login_id, "Folder": name}).to_list(length=None)
    if train_ids:
       return False
    deleted = await collection_folders.delete_one({"_id": folder["_id"]})
    if deleted.deleted_count > 0:
        return True
    return False

async def db_change_profile(login_id: str, new_name: str) -> bool:
    updated = await collection_users.update_one({"login_id": login_id}, {"$set": {"username": new_name}})
    if updated.modified_count > 0:
        return True
    return False

async def db_change_password(login_id: str, current_password: str, new_password: str) -> str:
    user = await collection_users.find_one({"login_id": login_id})
    if not user or not auth.verify_pw(current_password, user["password"]):
        return "incorrect"

    updated = await collection_users.update_one(
        {"login_id": login_id}, 
        {"$set": {"password": auth.generate_hashed_pw(new_password)}}
    )
    
    if updated.modified_count > 0:
        return "success"

    return "failed"
