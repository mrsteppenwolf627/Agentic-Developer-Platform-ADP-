import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';

export const NotFound = () => {
  return (
    <div className="min-h-screen bg-[var(--bg-primary)] flex items-center justify-center px-4">
      <motion.div
        className="text-center"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-6xl font-bold text-[var(--text-primary)] mb-4">404</h1>
        <p className="text-xl text-[var(--text-secondary)] mb-8">Página no encontrada</p>
        <Link 
          to="/dashboard" 
          className="bg-[var(--accent)] text-white px-6 py-3 rounded-lg font-medium hover:bg-[var(--accent-hover)] transition-colors inline-block"
        >
          Volver al Inicio
        </Link>
      </motion.div>
    </div>
  );
};