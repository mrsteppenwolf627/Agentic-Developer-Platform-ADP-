import { useAuthStore } from '../../store/authStore';

export const UserProfile = () => {
  const { user } = useAuthStore();
  
  if (!user) return null;
  
  return (
    <div className="p-4 bg-white rounded-xl border border-[var(--border)] mb-6 shadow-[var(--shadow-light)]">
      <h3 className="font-semibold text-[var(--text-primary)]">Perfil</h3>
      <p className="text-sm text-[var(--text-secondary)]">{user.email}</p>
      <div className="mt-2 text-xs bg-[var(--bg-secondary)] inline-block px-2 py-1 rounded">
        Rol: {user.role}
      </div>
    </div>
  );
};