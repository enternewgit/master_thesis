# %%
from pymongo import MongoClient
from bson import ObjectId

# MongoDB接続
client = MongoClient("mongodb://localhost:27017/")
db = client["word_haku"]  # データベース名を指定

# 旧コレクション
eegs_collection = db["eegs"]
counter_collection = db["counter"]

# 新コレクション
eegs_v2_collection = db["eegs_v2"]
counter_v2_collection = db["counter_v2"]

counter_docs = {doc["_id"]: doc for doc in counter_collection.find()}

#%%
# eegsの変換処理
eegs_v2_data = {}

for doc in eegs_collection.find():
    train_id = doc["train_id"]

    if train_id not in eegs_v2_data:
        eegs_v2_data[train_id] = {
            "_id": ObjectId(),
            "train_id": train_id,
            "words": [],
            "timestamps": [],
            "eegs": [],
            "eventMarker": [],
        }

    eegs_v2_data[train_id]["words"].append(doc["word"])
    eegs_v2_data[train_id]["timestamps"].append(doc["timestamp"])
    eegs_v2_data[train_id]["eegs"].append(
        [doc["data_0"], doc["data_1"], doc["data_2"], doc["data_3"]]
    )
#%%
#eegs_v2_dataの各要素に対してeventMarkerを追加
for train_id, data in eegs_v2_data.items():
    eventMarker = []
    previous_word = None
    for i, word in enumerate(data["words"]):
        if word != "" and word != previous_word and word not in (1, 2, 3):
            
            eventMarker.append({
                "word": word,
                "timestamp": data["timestamps"][i],
            })
        previous_word = word
    eegs_v2_data[train_id]["eventMarker"] = eventMarker
#%%
# 変換後のデータを保存
if eegs_v2_data:
    eegs_v2_collection.insert_many(eegs_v2_data.values())

#%%
# counter_v2の変換処理
counter_v2_data = []

for counter_doc in counter_docs.values():
    counter_v2_data.append(
        {
            "_id": counter_doc["_id"],
            "login_id": counter_doc["login_id"],
            "created_at": counter_doc["created_at"],
            "Folder": counter_doc["Folder"],
            "Memo":"",
            "expInfo": {
                "words": counter_doc["words"],
                "inputWords": counter_doc["inputWords"],
                "isShuffle": counter_doc["isShuffle"],
                "WordDisplayTime": counter_doc["WordDisplayTime"],
                "PauseTime": counter_doc["PauseTime"],
                "PauseCharacter": "+",
            },
            "eegSettings": {
                "DeviceName": counter_doc["DeviceName"],
                "SamplingRate": 256,
                "Duration": counter_doc["Duration"],
                "Interval": counter_doc["Interval"],
                "NotchFilter": counter_doc["NotchFilter"],
                "NotchFilterFrequency": counter_doc["NotchFilterFrequency"],
                "HighpassFilter": counter_doc["BandpassFilter"],
                "LowpassFilter": counter_doc["BandpassFilter"],
                "cutOffLow": counter_doc["cutOffLow"],
                "cutOffHigh": counter_doc["cutOffHigh"],
                "FFT": counter_doc["FFT"],
                "nbChannels": 4,
                "channelNames": ["TP9", "AF7", "AF8", "TP10","AUX"],
            },
        }
    )

# 変換後のデータを保存
if counter_v2_data:
    counter_v2_collection.insert_many(counter_v2_data)
