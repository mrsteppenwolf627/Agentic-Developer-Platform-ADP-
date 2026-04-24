import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { authService } from '../services/auth.service';
import { LoginRequest, RegisterRequest } from '../types/auth';
import { toast } from 'sonner';

export const useAuth = () => {
  const navigate = useNavigate();
  const { user, setUser, setAccessToken, logout: storeLogout, setIsLoading, isLoading } = useAuthStore();
  const [error, setError] = useState<string | null>(null);

  const login = async (credentials: LoginRequest) => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await authService.login(credentials);
      setAccessToken(response.access_token);
      setUser(response.user);
      toast.success(`Bienvenido, ${response.user.email}`);
      navigate('/dashboard');
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || 'Error al iniciar sesión';
      setError(errorMessage);
      toast.error(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const register = async (data: RegisterRequest) => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await authService.register(data);
      setAccessToken(response.access_token);
      setUser(response.user);
      toast.success('Cuenta creada exitosamente');
      navigate('/dashboard');
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || 'Error al crear cuenta';
      setError(errorMessage);
      toast.error(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    try {
      await authService.logout();
    } catch (err) {
      console.error('Logout error:', err);
    } finally {
      storeLogout();
      navigate('/login');
      toast.success('Sesión cerrada');
    }
  };

  const changePassword = async (oldPassword: string, newPassword: string) => {
    setIsLoading(true);
    setError(null);
    try {
      await authService.changePassword(oldPassword, newPassword);
      toast.success('Contraseña cambiada exitosamente');
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || 'Error al cambiar contraseña';
      setError(errorMessage);
      toast.error(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  return {
    user,
    isLoading,
    error,
    login,
    register,
    logout,
    changePassword,
    isAuthenticated: !!user,
  };
};