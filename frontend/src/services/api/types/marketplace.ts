/**
 * Marketplace types.
 */

export interface Marketplace {
  id: string;
  name: string;
  url: string;
  type: string;
  is_default: boolean;
  created_at?: string;
}

export interface MarketplacePlugin {
  id: string;
  marketplace_id: string;
  plugin_id?: string;
  remote_name: string;
  version?: string;
  installed_at?: string;
}

export interface MarketplaceSearchResult {
  name: string;
  description?: string;
  version?: string;
  source?: string;
  installed?: boolean;
  marketplace_id: string;
  marketplace_name: string;
}

export interface MarketplaceSearchResponse {
  results: MarketplaceSearchResult[];
  total: number;
  query: string;
  type: string;
}
