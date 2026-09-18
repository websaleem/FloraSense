export type Prediction = {
  classId: string;
  name: string;
  probability: number;
};

export type ScanRecord = {
  id: string;
  timestamp: number;
  imageUri: string;
  predictions: Prediction[];
};
