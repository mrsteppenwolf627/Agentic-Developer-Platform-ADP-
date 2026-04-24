import { useAuth } from '../../hooks/useAuth';
import { LogOut, User } from 'lucide-react';
import { motion } from 'framer-motion';

export const Header = () => {
  const { user, logout } = useAuth();

  return (
    <header className="border-b border-[var(--border)] bg-[var(--bg-primary)]">
      <div className="max-w-7xl mx-auto px-4 py-4 flex justify-between items-center">
        <h1 className="text-xl font-semibold text-[var(--text-primary)]">ADP</h1>
        
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <User size={16} className="text-[var(--text-secondary)]" />
            <span className="text-sm text-[var(--text-secondary)]">{user?.email}</span>
          </div>
          
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={logout}
            className="p-2 text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)] rounded-lg transition-colors"
          >
            <LogOut size={18} />
          </motion.button>
        </div>
      </div>
    </header>
  );
};