import api from './api';
import { LoginRequest, LoginResponse, RegisterRequest, RefreshResponse } from '../types/auth';

export const authService = {
  async login(credentials: LoginRequest): Promise<LoginResponse> {
    const { data } = await api.post('/auth/login', credentials);
    return data;
  },

  async register(data: RegisterRequest): Promise<LoginResponse> {
    const { data: response } = await api.post('/auth/register', {
      email: data.email,
      password: data.password,
    });
    return response;
  },

  async logout(): Promise<void> {
    await api.post('/auth/logout');
  },

  async refresh(): Promise<RefreshResponse> {
    const { data } = await api.post('/auth/refresh');
    return data;
  },

  async getMe() {
    const { data } = await api.get('/auth/me');
    return data;
  },

  async changePassword(oldPassword: string, newPassword: string): Promise<void> {
    await api.post('/auth/change-password', {
      old_password: oldPassword,
      new_password: newPassword,
    });
  },

  async forgotPassword(email: string): Promise<void> {
    await api.post('/auth/forgot-password', { email });
  },

  async resetPassword(token: string, newPassword: string): Promise<void> {
    await api.post('/auth/reset-password', {
      token,
      new_password: newPassword,
    });
  },
};