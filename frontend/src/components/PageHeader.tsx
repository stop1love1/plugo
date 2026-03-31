type PageHeaderProps = {
  title: string;
  subtitle?: string;
  children?: React.ReactNode; // action buttons go here
  /** e.g. mb-4 when the page uses a fixed viewport-height layout below */
  className?: string;
};

export function PageHeader({ title, subtitle, children, className = "mb-8" }: PageHeaderProps) {
  return (
    <div className={`flex items-center justify-between ${className}`}>
      <div>
        <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
        {subtitle && <p className="text-gray-500 mt-1">{subtitle}</p>}
      </div>
      {children && <div className="flex gap-2">{children}</div>}
    </div>
  );
}
