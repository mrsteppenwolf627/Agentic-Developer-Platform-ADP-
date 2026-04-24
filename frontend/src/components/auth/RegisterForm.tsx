import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useAuth } from '../../hooks/useAuth';
import { registerSchema } from '../../utils/validators';
import { motion } from 'framer-motion';
import { Loader } from 'lucide-react';

export const RegisterForm = () => {
  const { register: registerUser, isLoading, error } = useAuth();
  const { register, handleSubmit, formState: { errors } } = useForm({
    resolver: zodResolver(registerSchema),
  });

  const onSubmit = async (data: any) => {
    await registerUser(data);
  };

  return (
    <motion.form
      onSubmit={handleSubmit(onSubmit)}
      className="max-w-sm mx-auto space-y-4"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <div>
        <label className="block text-sm font-medium text-[var(--text-primary)] mb-1">
          Email
        </label>
        <input
          type="email"
          {...register('email')}
          className="w-full px-3 py-2 border border-[var(--border)] rounded-lg text-[var(--text-primary)] placeholder-[var(--text-tertiary)] focus:outline-none focus:border-[var(--accent)] transition-colors"
          placeholder="tu@email.com"
        />
        {errors.email && (
          <p className="text-[var(--error)] text-sm mt-1">{errors.email.message?.toString()}</p>
        )}
      </div>

      <div>
        <label className="block text-sm font-medium text-[var(--text-primary)] mb-1">
          Contraseña
        </label>
        <input
          type="password"
          {...register('password')}
          className="w-full px-3 py-2 border border-[var(--border)] rounded-lg text-[var(--text-primary)] placeholder-[var(--text-tertiary)] focus:outline-none focus:border-[var(--accent)] transition-colors"
          placeholder="••••••••"
        />
        {errors.password && (
          <p className="text-[var(--error)] text-sm mt-1">{errors.password.message?.toString()}</p>
        )}
      </div>

      <div>
        <label className="block text-sm font-medium text-[var(--text-primary)] mb-1">
          Confirmar Contraseña
        </label>
        <input
          type="password"
          {...register('password_confirm')}
          className="w-full px-3 py-2 border border-[var(--border)] rounded-lg text-[var(--text-primary)] placeholder-[var(--text-tertiary)] focus:outline-none focus:border-[var(--accent)] transition-colors"
          placeholder="••••••••"
        />
        {errors.password_confirm && (
          <p className="text-[var(--error)] text-sm mt-1">{errors.password_confirm.message?.toString()}</p>
        )}
      </div>

      {error && (
        <div className="bg-[var(--error-light)] border border-[var(--error)] rounded-lg p-3 text-[var(--error)] text-sm">
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={isLoading}
        className="w-full bg-[var(--accent)] text-white py-2 rounded-lg font-medium hover:bg-[var(--accent-hover)] disabled:opacity-50 transition-colors flex items-center justify-center gap-2 mt-4"
      >
        {isLoading ? (
          <>
            <Loader size={18} className="animate-spin" />
            Creando cuenta...
          </>
        ) : (
          'Registrarse'
        )}
      </button>
    </motion.form>
  );
};