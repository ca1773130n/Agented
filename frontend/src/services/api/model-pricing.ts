/**
 * Model pricing API module.
 */
import { apiFetch } from './client';

export interface ModelPricingInfo {
  id: string;
  name: string;
  inputPricePer1M: number;
  outputPricePer1M: number;
  contextWindow: number;
  speed: 'fast' | 'medium' | 'slow';
}

export interface ModelPricingResponse {
  models: ModelPricingInfo[];
}

export const modelPricingApi = {
  getModels: async (): Promise<ModelPricingResponse> => {
    return apiFetch<ModelPricingResponse>('/api/models/pricing');
  },
};
