import "@testing-library/jest-dom/vitest";

// jsdom's File polyfill lacks Blob.text(); used by file-upload components.
if (typeof File !== "undefined" && typeof File.prototype.text !== "function") {
  File.prototype.text = function (): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(reader.error);
      reader.readAsText(this);
    });
  };
}
