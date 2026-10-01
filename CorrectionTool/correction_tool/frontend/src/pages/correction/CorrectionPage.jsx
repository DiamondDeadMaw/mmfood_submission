import { useEffect, useState, useRef, useMemo } from "react"
import "./correction.css"
import { makePostRequest } from "../../constants"
import InteractionButton from "../../components/InteractionButton"
import TextInput from "../../components/TextInput"

export default function CorrectionPage({ username, projectName, setCompletionData }) {
  const [pageData, setPageData] = useState({
    text: null,
    extracted_json: null,
    corrected_json: null,
    corrections: null,
    detected_errors: null,
    id: null
  })

  const [matchingKeySrc, setMatchingKeySrc] = useState("")
  const [matchingKeyTarget, setMatchingKeyTarget] = useState("")
  const [sourceFile, setSourceFile] = useState(null)
  const [extractedFile, setExtractedFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0);

  const [correctedJson, setCorrectedJson] = useState(null)
  const [correctionLog, setCorrectionLog] = useState([])
  const [dismissedFlags, setDismissedFlags] = useState([])
  const [highlightedText, setHighlightedText] = useState("")
  const [highlightMatches, setHighlightMatches] = useState([])
  const [currentMatchIndex, setCurrentMatchIndex] = useState(0)
  const [selectedField, setSelectedField] = useState("")
  const [errorType, setErrorType] = useState("")
  const [newErrorType, setNewErrorType] = useState("")
  const [newErrorDescription, setNewErrorDescription] = useState("")
  const [evidenceText, setEvidenceText] = useState("")
  const [correctedValue, setCorrectedValue] = useState("")
  const [isCreatingNewError, setIsCreatingNewError] = useState(false)
  const [isCreatingNewField, setIsCreatingNewField] = useState(false)
  const [newFieldPath, setNewFieldPath] = useState("")

  const [fetchComplete, setFetchComplete] = useState(false)

  const sourceTextRef = useRef(null)

  const [errorTypes, setErrorTypes] = useState([])

  useEffect(() => {
    fetchData()
  }, [])

  useEffect(() => {
    if (pageData.extracted_json) {
      setCorrectedJson(JSON.parse(JSON.stringify(pageData.extracted_json)))
    }
  }, [pageData.extracted_json])

  async function fetchData() {
    const response = await makePostRequest("get_correction_data", {
      project_name: projectName,
      username: username
    })

    setFetchComplete(true)
    if (response.ok && response.correction_data) {
      setErrorTypes(response.correction_data.error_types || [])
      setPageData((prev) => ({ ...prev, ...response.correction_data }))
      setCompletionData({
        total_num: response.correction_data.total_num,
        total_corrected: response.correction_data.total_corrected,
        total_corrected_by_user: response.correction_data.total_corrected_by_user
      })
    }
  }
  const handleTextHighlight = () => {
    const selection = window.getSelection().toString().trim()
    if (selection) {
      setEvidenceText(selection)
    }
  }
  const isEmptyData =
    !pageData.text &&
    !pageData.extracted_json &&
    !pageData.corrected_json &&
    !pageData.corrections

  async function uploadFileInChunks(file, onProgress) {
    const chunkSize = 1024 * 1024 * 5;
    const totalChunks = Math.ceil(file.size / chunkSize);
    const uploadID = `${file.name}-${Date.now()}`;

    for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
      const start = chunkIndex * chunkSize;
      const end = Math.min(start + chunkSize, file.size);
      const chunk = file.slice(start, end);

      const formData = new FormData();
      formData.append("chunk", chunk);
      formData.append("upload_id", uploadID);
      formData.append("chunk_index", chunkIndex);
      formData.append("total_chunks", totalChunks);
      
      const res = await fetch("/api/upload_chunk", {
        method: "POST",
        body: formData
      });

      if (!res.ok) {
        throw new Error(`Chunk upload failed: ${res.statusText}`);
      }

      onProgress((chunkIndex + 1) / totalChunks * 100);
   }
   return uploadID;
  }

  const handleSubmit = async () => {
    if (!sourceFile || !extractedFile || !matchingKeySrc || !matchingKeyTarget) {
      return alert("Select both files and enter a matching key.")
    }
    setUploading(true);
    setUploadProgress(0);
    try {

      const sourceUploadId = await uploadFileInChunks(sourceFile, (progress) => {
        setUploadProgress(progress / 2);
      });

      const extractedUploadId = await uploadFileInChunks(extractedFile, (progress) => {
        setUploadProgress(50 + progress / 2);
      });

      const finalizeData = new FormData()
      const formData = new FormData()
      finalizeData.append("project_name", projectName);
      finalizeData.append("matching_key_src", matchingKeySrc);
      finalizeData.append("matching_key_target", matchingKeyTarget);
      finalizeData.append("source_upload_id", sourceUploadId);
      finalizeData.append("source_filename", sourceFile.name);
      finalizeData.append("extracted_upload_id", extractedUploadId);
      finalizeData.append("extracted_filename", extractedFile.name);

      console.log("Going to upload data", finalizeData)

      const res = await fetch("/api/process_uploaded_data", {
        method: "POST",
        body: finalizeData,
      });

      if (!res.ok) {
        throw new Error(`Data upload failed: ${res.statusText}`);
      }
      alert("Data uploaded successfully")
      await fetchData()
    } catch (err) {
      console.error(err)
      alert("Upload failed: " + err.message)
    } finally {
      setUploading(false);
      setUploadProgress(0);
    }
  }

  const highlightTextInSource = (text) => {
    if (!text || !pageData.text) return

    const matches = []
    let startIndex = 0
    
    while (true) {
      const index = pageData.text.toLowerCase().indexOf(text.toLowerCase(), startIndex)
      if (index === -1) break
      matches.push(index)
      startIndex = index + 1
    }

    setHighlightMatches(matches)
    setHighlightedText(text)
    setCurrentMatchIndex(0)

    if (matches.length > 0) {
      scrollToMatch(0, matches)
    }
  }

  const scrollToMatch = (matchIndex, matches = highlightMatches) => {
    if (!sourceTextRef.current || matches.length === 0) return

    const sourceElement = sourceTextRef.current
    const text = pageData.text
    const matchPosition = matches[matchIndex]

    const totalLength = text.length
    const scrollHeight = sourceElement.scrollHeight
    const elementHeight = sourceElement.clientHeight
    const scrollPosition = Math.max(0, (matchPosition / totalLength) * scrollHeight - elementHeight / 2)
    
    sourceElement.scrollTop = scrollPosition
  }

  const handleFieldClick = (path, value) => {
    if (selectedField === path && highlightMatches.length > 0) {
      cycleToNextMatch()
      return
    }
    
    setSelectedField(path)
    if (value && typeof value === 'string') {
      highlightTextInSource(value)
    }
  }

  const cycleToNextMatch = () => {
    if (highlightMatches.length === 0) return
    
    const nextIndex = (currentMatchIndex + 1) % highlightMatches.length
    setCurrentMatchIndex(nextIndex)
    scrollToMatch(nextIndex)
  }

  const getHighlightedSourceText = () => {
    if (!pageData.text || !highlightedText || highlightMatches.length === 0) {
      return pageData.text
    }

    let result = pageData.text
    const matches = [...highlightMatches].sort((a, b) => b - a)

    matches.forEach((matchIndex, i) => {
      const isCurrentMatch = highlightMatches.indexOf(matchIndex) === currentMatchIndex
      const className = isCurrentMatch ? 'highlight-current' : 'highlight-match'
      const before = result.substring(0, matchIndex)
      const match = result.substring(matchIndex, matchIndex + highlightedText.length)
      const after = result.substring(matchIndex + highlightedText.length)
      result = `${before}<span class="${className}">${match}</span>${after}`
    })

    return result
  }

  const isDismissed = (error) => dismissedFlags.some(f => f.field === error.field)

  const flagsAt = (path) => {
    const matching = (pageData.detected_errors || []).filter(error =>
      error.field === path || path.includes(error.field)
    )
    return {
      active: matching.find(error => !isDismissed(error)),
      dismissed: matching.find(error => isDismissed(error)),
    }
  }

  const rebuildCorrectedJson = (log) => {
    const rebuilt = JSON.parse(JSON.stringify(pageData.extracted_json))
    log.forEach(c => {
      if (c.is_new_field) {
        createFieldPath(rebuilt, c.field, c.corrected_value)
      } else {
        setFieldValue(rebuilt, c.field, c.corrected_value)
      }
    })
    return rebuilt
  }

  const handleRemoveCorrection = (index) => {
    const newLog = correctionLog.filter((_, i) => i !== index)
    setCorrectionLog(newLog)
    setCorrectedJson(rebuildCorrectedJson(newLog))
  }

  const handleDismissFlag = (flag) => {
    setDismissedFlags(prev => [...prev, {
      field: flag.field,
      error_type: flag.error_type,
      suggested: flag.source_value,
      evidence: evidenceText,
      timestamp: new Date().toISOString(),
    }])
    setSelectedField("")
    setEvidenceText("")
  }

  const handleRestoreFlag = (field) => {
    setDismissedFlags(prev => prev.filter(f => f.field !== field))
  }

  const renderJsonField = (obj, path = '') => {
    if (typeof obj !== 'object' || obj === null) {
      const { active: detectedError, dismissed: dismissedError } = flagsAt(path)
      const isDetectedError = !!detectedError

      const isChanged = correctionLog.some(log => log.field === path)

      return (
        <span
          className={`json-value ${isDetectedError ? 'detected-error' : ''} ${!isDetectedError && dismissedError ? 'flag-dismissed' : ''} ${isChanged ? 'field-changed' : ''} ${selectedField === path ? 'field-selected' : ''}`}
          onClick={() => handleFieldClick(path, obj)}
          title={detectedError ? `Detected Error: ${detectedError.error_type}, Suggested: ${detectedError.source_value}` : (dismissedError ? 'Flag dismissed as a false positive' : '')}
        >
          {typeof obj === 'string' ? `"${obj}"` : String(obj)}
        </span>
      )
    }

    if (Array.isArray(obj)) {
      return (
        <div className="json-array">
          [
          {obj.map((item, index) => (
            <div key={index} className="json-array-item">
              {renderJsonField(item, `${path}[${index}]`)}
              {index < obj.length - 1 && ','}
            </div>
          ))}
          ]
        </div>
      )
    }

    return (
      <div className="json-object">
        {'{'}
        {Object.entries(obj).map(([key, value], index, arr) => {
          const fieldPath = path ? `${path}.${key}` : key
          const { active: detectedError, dismissed: dismissedError } = flagsAt(fieldPath)
          const isDetectedError = !!detectedError

          return (
            <div key={key} className="json-field">
              <span
                className={`json-key ${isDetectedError ? 'detected-error' : ''} ${!isDetectedError && dismissedError ? 'flag-dismissed' : ''}`}
                title={detectedError ? `Detected Error: ${detectedError.error_type}` : ''}
              >
                "{key}"
              </span>
              : {renderJsonField(value, fieldPath)}
              {index < arr.length - 1 && ','}
            </div>
          )
        })}
        {'}'}
      </div>
    )
  }

  const handleAddCorrection = () => {
    const finalFieldPath = isCreatingNewField ? newFieldPath : selectedField
    
    if (!finalFieldPath || !errorType || !correctedValue) {
      alert('Please provide a field path, error type, and corrected value')
      return
    }

    const finalErrorType = isCreatingNewError ? newErrorType : errorType
    const originalValue = isCreatingNewField ? null : getFieldValue(correctedJson, finalFieldPath)

    const correction = {
      field: finalFieldPath,
      error_type: finalErrorType,
      evidence: evidenceText,
      original_value: originalValue,
      corrected_value: correctedValue,
      timestamp: new Date().toISOString(),
      is_new_field: isCreatingNewField
    }

    const newCorrectedJson = { ...correctedJson }

    if (isCreatingNewField) {
      createFieldPath(newCorrectedJson, finalFieldPath, correctedValue)
    } else {
      setFieldValue(newCorrectedJson, finalFieldPath, correctedValue)
    }
    
    setCorrectedJson(newCorrectedJson)

    setCorrectionLog(prev => [...prev.filter(log => log.field !== finalFieldPath), correction])

    setSelectedField("")
    setErrorType("")
    setNewErrorType("")
    setEvidenceText("")
    setCorrectedValue("")
    setIsCreatingNewError(false)
    setIsCreatingNewField(false)
    setNewFieldPath("")
  }

  const getFieldValue = (obj, path) => {
    return path.split('.').reduce((current, key) => {
      if (key.includes('[') && key.includes(']')) {
        const arrayKey = key.substring(0, key.indexOf('['))
        const index = parseInt(key.substring(key.indexOf('[') + 1, key.indexOf(']')))
        return current?.[arrayKey]?.[index]
      }
      return current?.[key]
    }, obj)
  }

  const setFieldValue = (obj, path, value) => {
    const keys = path.split('.')
    let current = obj
    
    for (let i = 0; i < keys.length - 1; i++) {
      const key = keys[i]
      if (key.includes('[') && key.includes(']')) {
        const arrayKey = key.substring(0, key.indexOf('['))
        const index = parseInt(key.substring(key.indexOf('[') + 1, key.indexOf(']')))
        current = current[arrayKey][index]
      } else {
        current = current[key]
      }
    }
    
    const finalKey = keys[keys.length - 1]
    if (finalKey.includes('[') && finalKey.includes(']')) {
      const arrayKey = finalKey.substring(0, finalKey.indexOf('['))
      const index = parseInt(finalKey.substring(finalKey.indexOf('[') + 1, finalKey.indexOf(']')))
      current[arrayKey][index] = value
    } else {
      current[finalKey] = value
    }
  }

  const createFieldPath = (obj, path, value) => {
    const keys = path.split('.')
    let current = obj
    
    for (let i = 0; i < keys.length - 1; i++) {
      const key = keys[i]
      if (key.includes('[') && key.includes(']')) {
        const arrayKey = key.substring(0, key.indexOf('['))
        const index = parseInt(key.substring(key.indexOf('[') + 1, key.indexOf(']')))
        if (!current[arrayKey]) current[arrayKey] = []
        if (!current[arrayKey][index]) current[arrayKey][index] = {}
        current = current[arrayKey][index]
      } else {
        if (!current[key]) current[key] = {}
        current = current[key]
      }
    }
    
    const finalKey = keys[keys.length - 1]
    if (finalKey.includes('[') && finalKey.includes(']')) {
      const arrayKey = finalKey.substring(0, finalKey.indexOf('['))
      const index = parseInt(finalKey.substring(finalKey.indexOf('[') + 1, finalKey.indexOf(']')))
      if (!current[arrayKey]) current[arrayKey] = []
      current[arrayKey][index] = value
    } else {
      current[finalKey] = value
    }
  }

  const handleSaveAndNext = async () => {
    const payload = {
      text: pageData.text,
      extracted_json: pageData.extracted_json,
      corrected_json: correctedJson,
      correction_log: correctionLog,
      dismissed_flags: dismissedFlags,
      detected_errors: pageData.detected_errors,
      id: pageData.id,
      username: username,
      project_name: projectName
    }

    try {
      const response = await makePostRequest("add_corrected_document", payload)
      if (response.ok) {
        alert("Document saved successfully")
        await fetchData()
        setCorrectionLog([])
        setDismissedFlags([])
      } else {
        alert("Failed to save document")
      }
    } catch (err) {
      console.error(err)
      alert("Error saving document: " + err.message)
    }
  }

  const handleMarkCorrectAndNext = async () => {
    const payload = {
      text: pageData.text,
      extracted_json: pageData.extracted_json,
      corrected_json: pageData.extracted_json,
      correction_log: [],
      dismissed_flags: dismissedFlags,
      detected_errors: pageData.detected_errors,
      id: pageData.id,
      username: username,
      project_name: projectName
    }

    try {
      const response = await makePostRequest("add_corrected_document", payload)
      if (response.ok) {
        alert("Document marked as correct")
        await fetchData()
        setCorrectionLog([])
        setDismissedFlags([])
      } else {
        alert("Failed to mark document as correct")
      }
    } catch (err) {
      console.error(err)
      alert("Error marking document as correct: " + err.message)
    }
  }

  function handleCreateError(newErrorData) {
    makePostRequest("new_error_type", newErrorData)
    setErrorTypes(prev => [...prev, newErrorData])
    setNewErrorType("")
    setNewErrorDescription("")
    setIsCreatingNewError(false)
    alert("New error type created successfully")
  }

  const memoizedSourceHTML = useMemo(() => {
    return getHighlightedSourceText()
  }, [pageData.text, highlightedText, currentMatchIndex])

  return (
    <div className="correction-page">
      {isEmptyData && !fetchComplete ? (
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          width: "100vw",
          height: "calc(100vh - 40px)",
        }}>
          Attempting to fetch data...
        </div>
      ) : (
        isEmptyData && fetchComplete ? (
        <div className="input-section">
          <h2 className="card-header">Input data for a new project</h2>
          <h3 className="card-subheader">Ensure the source has a column "text"</h3>
          <div className="field-group">
            <label>Enter Matching Key (Source)</label>
            <TextInput placeholder="Matching key" setValue={setMatchingKeySrc} />
          </div>

          <div className="field-group">
            <label>Enter Matching Key (Target)</label>
            <TextInput placeholder="Matching key" setValue={setMatchingKeyTarget} />
          </div>

          <div className="field-group">
            <label>Source Data (CSV)</label>
            <input
              type="file"
              accept="application/csv"
              onChange={(e) => setSourceFile(e.target.files[0] || null)}
            />
          </div>

          <div className="field-group">
            <label>Extracted Data (JSON)</label>
            <input
              type="file"
              accept="application/json"
              onChange={(e) => setExtractedFile(e.target.files[0] || null)}
            />
          </div>

          {uploading && (
            <div className="progress-container">
              <label>Uploading: {Math.round(uploadProgress)}%</label>
              <progress value={uploadProgress} max="100" style={{ width: '100%' }} />
            </div>
          )}

          <InteractionButton
            text={uploading ? "Uploading…" : "Submit Data"}
            onButtonPress={handleSubmit}
            color="#007BFF"
            width="180px"
          />
        </div>
      ) :(
        <div className="correction-interface">

          <div className="correction-content">
            <div className="source-panel">
              <div className="panel-header">
                <h3>Source Text</h3>
                {highlightMatches.length > 0 && (
                  <div className="match-navigation">
                    <span>Match {currentMatchIndex + 1} of {highlightMatches.length}</span>
                    <button onClick={cycleToNextMatch}>Next Match</button>
                  </div>
                )}
              </div>
              <div 
                ref={sourceTextRef}
                onMouseUp={handleTextHighlight}
                className="source-text"
                dangerouslySetInnerHTML={{ __html: getHighlightedSourceText() }}
              />
            </div>

            <div className="json-panel">
              <h3>Extracted JSON</h3>
              <div className="json-container">
                {renderJsonField(correctedJson)}
              </div>
            </div>

            <div className="correction-panel">
              <h3>Corrections</h3>

              <div className="field-group">
                <label>
                  <input
                    type="checkbox"
                    checked={isCreatingNewField}
                    onChange={(e) => {
                      setIsCreatingNewField(e.target.checked)
                      if (e.target.checked) {
                        setSelectedField("")
                      }
                    }}
                  />
                  Create New Field
                </label>
              </div>

              {isCreatingNewField && (
                <div className="field-group">
                  <label>New Field Path:</label>
                  <TextInput 
                    placeholder="e.g., ingredients.new_item or recipe_tags"
                    setValue={setNewFieldPath}
                  />
                </div>
              )}
              
              {(selectedField || (isCreatingNewField && newFieldPath)) && (
                <div className="selected-field-info">
                  <strong>Selected Field:</strong> {isCreatingNewField ? newFieldPath : selectedField}
                  <br />
                  {!isCreatingNewField && (
                    <>
                      <strong>Current Value:</strong> {JSON.stringify(getFieldValue(correctedJson, selectedField))}
                    </>
                  )}
                  {isCreatingNewField && (
                    <strong>Status:</strong>
                  )}
                </div>
              )}

              {!isCreatingNewField && selectedField && flagsAt(selectedField).active && (
                <div className="dismiss-box">
                  <div>
                    <strong>Pipeline flag:</strong> {flagsAt(selectedField).active.error_type}
                    {flagsAt(selectedField).active.source_value ? ` (suggested: ${flagsAt(selectedField).active.source_value})` : ''}
                  </div>
                  <InteractionButton
                    text="Dismiss Flag (false positive)"
                    onButtonPress={() => handleDismissFlag(flagsAt(selectedField).active)}
                    color="#6c757d"
                    fcolor={"white"}
                    width="100%"
                  />
                </div>
              )}

              <div className="field-group">
                <label>Error Type:</label>
                <select 
                  value={errorType} 
                  onChange={(e) => {
                    setErrorType(e.target.value)
                    setIsCreatingNewError(e.target.value === 'create_new')
                  }}
                >
                  <option value="">Select Error Type</option>
                  {errorTypes.map(type => (
                    <option key={type.name} value={type.name}>{type.name}</option>
                  ))}
                  <option value="create_new">+ Create New Error Type</option>
                </select>
                <p className="error-description">
                  {
                    errorTypes.find(type => type.name === errorType)?.description ||
                    (isCreatingNewError ? "Enter a new error type below." : "Select an error type from the list.")
                  }
                </p>
              </div>

              {isCreatingNewError && (
                <>
                <div className="field-group">
                  <label>New Error Type:</label>
                  <TextInput 
                    placeholder="Enter new error type"
                    setValue={setNewErrorType}
                  />
                </div>
                <div className="field-group">
                  <label>Description:</label>
                  <TextInput 
                    placeholder="Enter new error type"
                    setValue={setNewErrorDescription}
                  />
                </div>
                <InteractionButton onButtonPress={handleCreateError} args={[
                  {
                    "name" : newErrorType,
                    "description" : newErrorDescription
                  }
                ]} text={"Create"}
                width={"100%"}
                />
                </>
                
              )}

              <div className="field-group">
                <label>Evidence from Source:</label>
                <textarea
                  value={evidenceText}
                  onChange={(e) => setEvidenceText(e.target.value)}
                  placeholder="Highlight and copy relevant text from source as evidence"
                  rows={3}
                />
              </div>

              <div className="field-group">
                <label>Corrected Value:</label>
                <TextInput
                  placeholder="Enter corrected value"
                  setValue={setCorrectedValue}
                />
              </div>

              <div className="correction-btn-container">
                <InteractionButton
                text="Add Correction"
                onButtonPress={handleAddCorrection}
                color="#343a40"
                fcolor={"white"}
                width="100%"
              />
              <InteractionButton
              text="Save & Next"
              onButtonPress={handleSaveAndNext}
              color="green"
              width="100%"
              height={"40px"}
              fcolor={"white"}
            />
            <InteractionButton
              text="Mark Correct & Next"
              onButtonPress={handleMarkCorrectAndNext}
              color="orange"
              width="100%"
              height={"40px"}
              fcolor={"white"}
            />

              <div className="correction-log">
                <h4>Applied Corrections ({correctionLog.length})</h4>
                {correctionLog.map((correction, index) => (
                  <div key={index} className="correction-item">
                    <strong>{correction.field}</strong> - {correction.error_type}
                    {correction.is_new_field && <span className="new-field-badge">NEW</span>}
                    <button className="log-remove-btn" onClick={() => handleRemoveCorrection(index)}>Remove</button>
                    <br />
                    <span className="correction-change">
                      {correction.is_new_field
                        ? `Added: "${correction.corrected_value}"`
                        : `"${correction.original_value}" → "${correction.corrected_value}"`
                      }
                    </span>
                  </div>
                ))}
              </div>

              <div className="correction-log">
                <h4>Dismissed Flags ({dismissedFlags.length})</h4>
                {dismissedFlags.map((flag) => (
                  <div key={flag.field} className="correction-item">
                    <strong>{flag.field}</strong> - {flag.error_type}
                    <button className="log-remove-btn" onClick={() => handleRestoreFlag(flag.field)}>Restore</button>
                    <br />
                    <span className="correction-change">Marked as a false positive</span>
                  </div>
                ))}
              </div>
                </div>
            </div>
          </div>
        </div>
      )
      )}
    </div>
  )
}