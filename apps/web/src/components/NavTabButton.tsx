import React from 'react';

interface Props {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}

export const NavTabButton: React.FC<Props> = ({ active, onClick, icon, label }) => (
  <button
    type="button"
    onClick={onClick}
    aria-current={active ? 'page' : undefined}
    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-colors ${
      active ? 'bg-paper text-ink shadow-sm' : 'text-subtle hover:text-ink'
    }`}
  >
    {icon} {label}
  </button>
);
