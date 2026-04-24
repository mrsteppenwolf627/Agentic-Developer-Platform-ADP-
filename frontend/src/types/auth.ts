export interface User {
  id: string;
  email: string;
  role: 'admin' | 'developer' | 'user';
  avatar?: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  expires_in: number;
  user: User;
}

export interface RegisterRequest {
  email: string;
  password: string;
  password_confirm: string;
}

export interface RefreshResponse {
  access_token: string;
  expires_in: number;
}