type FormFieldProps = {
  label: string;
  children: React.ReactNode;
  error?: string;
  className?: string;
  required?: boolean;
};

export function FormField({ label, children, error, className = "", required }: FormFieldProps) {
  return (
    <div className={className}>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        {label}{required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      {children}
      {error && <p className="text-sm text-red-500 mt-1">{error}</p>}
    </div>
  );
}
