import { motion } from 'framer-motion';
import { AlertCircle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export const SessionExpiredModal = ({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) => {
  const navigate = useNavigate();

  if (!isOpen) return null;

  return (
    <motion.div
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
    >
      <motion.div
        className="bg-white rounded-lg p-6 max-w-sm"
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
      >
        <div className="flex gap-3 mb-4">
          <AlertCircle className="text-orange-500" />
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Sesión Expirada</h2>
        </div>
        <p className="text-[var(--text-secondary)] mb-6">
          Tu sesión ha expirado. Por favor, inicia sesión nuevamente.
        </p>
        <motion.button
          whileHover={{ scale: 1.02 }}
          onClick={() => navigate('/login')}
          className="w-full bg-[var(--accent)] text-white py-2 rounded-lg font-medium"
        >
          Ir a Login
        </motion.button>
      </motion.div>
    </motion.div>
  );
};