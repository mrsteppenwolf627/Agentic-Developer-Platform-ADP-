import { z } from 'zod';

export const loginSchema = z.object({
  email: z.string().email('Email inválido').min(1, 'Email es requerido'),
  password: z.string().min(8, 'Mínimo 8 caracteres').min(1, 'Contraseña es requerida'),
});

export const registerSchema = z.object({
  email: z.string().email('Email inválido').min(1, 'Email es requerido'),
  password: z.string().min(8, 'Mínimo 8 caracteres'),
  password_confirm: z.string().min(8, 'Mínimo 8 caracteres'),
}).refine((data) => data.password === data.password_confirm, {
  message: "Las contraseñas no coinciden",
  path: ["password_confirm"],
});

export const taskSchema = z.object({
  title: z.string().min(1, 'Título requerido').max(100, 'Máximo 100 caracteres'),
  description: z.string().min(1, 'Descripción requerida').max(500, 'Máximo 500 caracteres'),
});

export const changePasswordSchema = z.object({
  old_password: z.string().min(8, 'Mínimo 8 caracteres'),
  new_password: z.string().min(8, 'Mínimo 8 caracteres'),
  new_password_confirm: z.string().min(8, 'Mínimo 8 caracteres'),
}).refine((data) => data.new_password === data.new_password_confirm, {
  message: "Las contraseñas nuevas no coinciden",
  path: ["new_password_confirm"],
});