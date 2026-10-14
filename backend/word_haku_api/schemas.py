from pydantic import BaseModel, Field, ConfigDict
from typing import Union, List, Optional, Tuple, Dict, Any, Literal, Annotated
from decouple import config
from bson import ObjectId
from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema

CSRF_KEY = config('CSRF_KEY')

class CsrfSettings(BaseModel):
    secret_key: str = CSRF_KEY

class EEGs(BaseModel):
    id: str
    #login_id: str
    train_id: str
    timestamp: float
    data_0: float
    data_1: float
    data_2: float
    data_3: float
    #data_4: float
    word: str

class EEGsBody(BaseModel):
    #login_id: str
    train_id: str = None
    timestamp: float
    data_0: float
    data_1: float
    data_2: float
    data_3: float
    #data_4: float
    word: str
    
class EEGsv2Base(BaseModel):
    timestamps: List[float]
    eegs: List[List[Union[float,None]]]
    words: Optional[List[str]]=None
    eventMarker: Optional[List[Dict[str, Any]]] = None

class EEGsv2(EEGsv2Base):
    id: str
    train_id: str

class EEGsv2Body(EEGsv2Base):
    pass

class TrainIdsBase(BaseModel):
    Folder: Optional[Union[str, List[str]]] = None
    words: Optional[Union[str, List[str]]] = None
    inputWords: Optional[Union[str, List[str]]] = None
    isShuffle: Optional[bool] = None
    Duration: Optional[int] = None
    Interval: Optional[int] = None
    NotchFilter: Optional[bool] = None
    NotchFilterFrequency: Optional[int] = None
    BandpassFilter: Optional[bool] = None
    cutOffLow: Optional[int] = None
    cutOffHigh: Optional[int] = None
    FFT: Optional[bool] = None
    DeviceName: Optional[str] = None
    WordDisplayTime: Optional[float] = None
    PauseTime: Optional[float] = None
    PauseCharacter: Optional[str] = None
    advanced: Optional[List[Tuple[str, float]]] = None
    nbChannels: Optional[int] = None
    channelNames: Optional[List[str]] = None
    
class TrainIds(TrainIdsBase):
    id: str
    login_id: str
    created_at: str

class TrainIdsBody(TrainIdsBase):
    pass

class SSExpInfo(BaseModel):
    words: Optional[Union[str, List[str]]] = None
    inputWords: Optional[Union[str, List[str]]] = None
    isShuffle: Optional[bool] = None
    WordDisplayTime: Optional[float] = None
    PauseTime: Optional[float] = None
    PauseCharacter: Optional[str] = None
    advancedInput: Optional[List[Tuple[str, float]]] = None

class EEGSettings(BaseModel):
    DeviceName: Optional[str] = None
    SamplingRate: Optional[int] = None
    Duration: Optional[int] = None
    Interval: Optional[int] = None
    NotchFilter: Optional[bool] = None
    NotchFilterFrequency: Optional[int] = None
    HighpassFilter: Optional[bool] = None
    LowpassFilter: Optional[bool] = None
    cutOffLow: Optional[float] = None
    cutOffHigh: Optional[float] = None
    FFT: Optional[bool] = None
    nbChannels: Optional[int] = None
    channelNames: Optional[List[str]] = None

class TrainIdsv2Base(BaseModel):
    expInfo: Optional[SSExpInfo] = None
    eegSettings: Optional[EEGSettings] = None
    Folder: Optional[Union[str, List[str]]] = None
    Memo: Optional[str] = None
    
class TrainIdsv2(TrainIdsv2Base):
    id: str
    login_id: str
    created_at: str

class TrainIdsv2Body(TrainIdsv2Base):
    pass

class TrainInfoWrapper(BaseModel):
    trainInfo: TrainIdsv2Body

class SuccessMsg(BaseModel):
    message: str

class LoginBody(BaseModel):
    login_id: str
    password: str

class SignupBody(BaseModel):
    username: str
    login_id: str
    password: str

class UserInfo(BaseModel):
    login_id: str
    username: str
    role: Literal['user', 'admin'] = 'user'

class Csrf(BaseModel):
    csrf_token: tuple

class Folders(BaseModel):
    id: str
    login_id: str
    name: str
    created_at: str
    item_count: int

class FoldersBody(BaseModel):
    name: str

class TagRequest(BaseModel):
    trainId: str
    tag: str

# GridFS用のObjectIdをPydanticで扱うためのクラス
class PyObjectId(ObjectId):
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler: GetCoreSchemaHandler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return v
        return ObjectId(str(v))

# 推論モデル用のスキーマ
class InfModelBase(BaseModel):
    train_id: List[str]
    name: str
    note: Optional[str] = None
    hyperparameters: Optional[Dict[str, Any]] = None
    input_shape: Optional[List[int]] = None
    output_labels: Optional[List[str]] = None
    model_file_id: Optional[PyObjectId] = None
    label_encoder_file_id: Optional[PyObjectId] = None

class InfModelCreate(InfModelBase):
    pass

class InfModelMetadata(InfModelBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    login_id: str
    created_at: str
    updated_at: str
    label_policy: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
    )

class WordData(BaseModel):
    data: List[List[Optional[float]]]  # null 値を許容
    word: Optional[str]  # word が None の場合を許容