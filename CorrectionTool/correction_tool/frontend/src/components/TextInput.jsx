import "./component_styles.css";

function TextInput({ setValue, placeholder = "", onKeyDown, width = null }) {
  const handleChange = (e) => {
    setValue(e.target.value);
  };

  const style = width ? { width } : {};

  return (
    <input
      type="text"
      className="text-input"
      placeholder={placeholder}
      onChange={handleChange}
      onKeyDown={onKeyDown}
      style={style}
    />
  );
}

export default TextInput;
