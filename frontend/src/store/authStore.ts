import { create } from 'zustand';
import { User } from '../types/auth';

interface AuthStore {
  user: User | null;
  accessToken: string | null;
  isLoading: boolean;
  
  // Acciones
  setUser: (user: User | null) => void;
  setAccessToken: (token: string | null) => void;
  setIsLoading: (loading: boolean) => void;
  logout: () => void;
  
  // Cargar desde localStorage al iniciar
  hydrate: () => void;
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  accessToken: null,
  isLoading: false,

  setUser: (user) => set({ user }),
  setAccessToken: (token) => {
    if (token) {
      localStorage.setItem('access_token', token);
    } else {
      localStorage.removeItem('access_token');
    }
    set({ accessToken: token });
  },
  setIsLoading: (loading) => set({ isLoading: loading }),
  
  logout: () => {
    localStorage.removeItem('access_token');
    set({ user: null, accessToken: null });
  },

  hydrate: () => {
    const token = localStorage.getItem('access_token');
    if (token) {
      set({ accessToken: token });
      // Aquí podrías hacer GET /auth/me para obtener user si lo deseas
    }
  },
}));