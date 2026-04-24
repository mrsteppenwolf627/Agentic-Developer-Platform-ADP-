import { useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { RegisterForm } from '../components/auth/RegisterForm';
import { motion } from 'framer-motion';

export const Register = () => {
  const navigate = useNavigate();
  const { user } = useAuthStore();

  useEffect(() => {
    if (user) {
      navigate('/dashboard');
    }
  }, [user, navigate]);

  return (
    <div className="min-h-screen bg-[var(--bg-primary)] flex items-center justify-center px-4">
      <motion.div
        className="w-full max-w-md bg-white p-8 rounded-2xl shadow-[var(--shadow-medium)] border border-[var(--border)]"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-3xl font-semibold text-center text-[var(--text-primary)] mb-2">
          Crear Cuenta
        </h1>
        <p className="text-center text-[var(--text-secondary)] mb-8 text-sm">
          Únete a la plataforma ADP
        </p>
        <RegisterForm />
        <div className="mt-6 text-center text-sm text-[var(--text-secondary)]">
          ¿Ya tienes cuenta?{' '}
          <Link to="/login" className="text-[var(--accent)] hover:underline font-medium">
            Inicia Sesión
          </Link>
        </div>
      </motion.div>
    </div>
  );
};