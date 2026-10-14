export interface EEGs {
  id?: string;
//   login_id: string
  train_id: string;
  timestamp: number;
  data_0: number;
  data_1: number;
  data_2: number;
  data_3: number;
  word: string;
}

export interface EEGsv2{
  id?: string;
  train_id?: string;
  timestamps: number[];
  eegs: number[][];
  words?: string[];
  eventMarker?: EventMarkerType[];
}

export interface eegSettings {
  DeviceName: string;
  FFT: boolean;
  NotchFilter: boolean;
  NotchFilterFrequency: number;
  HighpassFilter: boolean;
  LowpassFilter: boolean;
  cutOffLow: number;
  cutOffHigh: number;
  Duration: number;
  Interval: number;
  SamplingRate: number;
  nbChannels: number;
  channelNames: string[];
}

export interface EventMarkerType {
  word: string | null;
  timestamp: number;
}

export interface ExpInfo {
  words?: string[];
  inputWords?: string[];
  isShuffle?: boolean;
  WordDisplayTime?: number;
  PauseTime?: number;
  PauseCharacter?: string;
  advancedInput?: [string, number][];
}


export interface StreamData {
  data: number[];
  timestamp: number;
  info?: {
    samplingRate: number;
    channelNames: string[];
  };
  index?: number;
  bandPowers?: {
    delta: number[];
    theta: number[];
    alpha: number[];
    beta: number[];
    gamma: number[];
  };
}

export interface BandPowerData {
  time: number;
  delta: number[];
  theta: number[];
  alpha: number[];
  beta: number[];
  gamma: number[];
}


export interface JsonData {
  data: number[][];
  psd: number[][];
  bandPowers: {
    delta: number[];
    theta: number[];
    alpha: number[];
    beta: number[];
    gamma: number[];
  }
  info: { samplingRate: number; startTime: number  };
}

export interface Folder {
  name: string;
  item_count: number;
}

export interface CsrfToken {
  csrf_token: string;
}

export interface LoginBody {
  login_id: string;
  password: string;
}

export interface RegisterBody {
  username: string;
  login_id: string;
  password: string;
}

export interface UserInfo {
  uid: string;
  login_id: string;
  username: string;
  role?: string;
}

export interface Users {
  id: string;
  login_id: string;
  username: string;
  role?: string;
}

export interface TrainsProps {
  selectedUserId: string | null;
}

export interface TrainInfo {
  id?: string;
//   login_id: string;
//   created_at: string;
  Folder: string[];
  words: string[];
  inputWords: string[];
  isShuffle: boolean;
  Duration: number;
  Interval: number;
  NotchFilter: boolean;
  NotchFilterFrequency: number;
  LowpassFilter: boolean;
  HighpassFilter: boolean;
  cutOffLow: number;
  cutOffHigh: number;
  FFT: boolean;
  DeviceName: string;
  WordDisplayTime: number;
  PauseTime: number;
  PauseCharacter: string;
  advancedInput?: [string, number][];
  nbChannels: number;
  channelNames: string[];
}

export interface TrainInfov2{
  id?: string;
  created_at?: string;
  Folder: string[];
  Memo: string;
  expInfo: ExpInfo;
  eegSettings: eegSettings;
} 

export interface Folders {
  id: string;
  login_id: string;
  name: string;
  created_at: string;
  item_count: number;
}

export interface FoldersBody {
  name: string;
}

export interface InfModels {
  id: string;
  login_id: string;
  train_id: string;
  name: string;
  note: string;
  created_at: string;
  hyperparameters: {
    epochs: number;
    lr: number;
    target_length: number;
  };
  input_shape: number[];
  output_labels: string[];
  label_policy: {
    positive: string[];
    negative: string[];
  }
}
