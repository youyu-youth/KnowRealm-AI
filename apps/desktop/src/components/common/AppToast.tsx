import { Toast } from "@base-ui/react/toast";
import { appToast } from "@/components/common/appToastManager";

function ToastList() {
  const { toasts } = Toast.useToastManager();

  return (
    <Toast.Portal>
      <Toast.Viewport className="fixed right-5 bottom-5 z-50 flex w-[min(22rem,calc(100vw-2.5rem))] flex-col gap-2">
        {toasts.map((toast) => (
          <Toast.Root
            key={toast.id}
            toast={toast}
            role="status"
            className="bg-surface-overlay border-border-subtle rounded-md border px-4 py-3 data-ending:opacity-0"
          >
            <Toast.Description className="text-body-dense text-ink">
              {toast.description}
            </Toast.Description>
          </Toast.Root>
        ))}
      </Toast.Viewport>
    </Toast.Portal>
  );
}

export function AppToasts() {
  return (
    <Toast.Provider toastManager={appToast} limit={2} timeout={5000}>
      <ToastList />
    </Toast.Provider>
  );
}
